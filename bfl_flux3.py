import base64
import math
import time
from io import BytesIO

import numpy as np
import requests
import torch
from PIL import Image

from comfy_api.latest._input_impl.video_types import VideoFromFile

from .bfl_common import REQUEST_TIMEOUT_SECONDS, get_api_key


FLUX3_ENDPOINT = "https://api.bfl.ai/v1/flux-3-video"

POLL_INTERVAL_SECONDS = 8.0
GENERATION_TIMEOUT_SECONDS = 1200
MAX_POLL_RETRIES = 3

ASPECT_RATIOS = ["auto", "21:9", "2:1", "16:9", "4:3", "1:1", "3:4", "9:16"]
DURATIONS_5_20 = ["auto"] + [str(i) for i in range(5, 21)]
DURATIONS_5_15 = ["auto"] + [str(i) for i in range(5, 16)]
RESOLUTIONS = ["720p", "1080p"]

RESOLUTION_API = {
    "720p": "hd",
    "1080p": "fhd",
}

# Direct Black Forest Labs API pricing.
# 1 BFL credit = $0.01 USD.
#
# Full renders:
#   T2V/I2V: 17 credits/s HD, 29 credits/s FHD
#   V2V:     43 credits/s HD, 54 credits/s FHD
#
# Draft renders:
#   T2V/I2V: 6 credits/s
#   V2V:     12 credits/s
#
# Drafts are rendered at HD.
DIRECT_CREDITS_PER_SECOND = {
    "t2v": {"720p": 17.0, "1080p": 29.0},
    "i2v": {"720p": 17.0, "1080p": 29.0},
    "v2v": {"720p": 43.0, "1080p": 54.0},
}

DRAFT_CREDITS_PER_SECOND = {
    "t2v": 6.0,
    "i2v": 6.0,
    "v2v": 12.0,
}

MAX_KEYFRAMES = 10
MIN_IMAGE_SIDE = 256
MAX_IMAGE_ASPECT = 64.0


def _format_http_error(response):
    try:
        detail = response.json()
    except ValueError:
        detail = response.text

    return f"FLUX 3 API Error HTTP {response.status_code}: {detail}"


def _require_api_key(api_key_override=""):
    key = (api_key_override or "").strip() or get_api_key()

    if not key:
        raise Exception(
            "No Black Forest Labs API key set. "
            "Set BFL_API_KEY, create bfl_api_key.txt next to bfl_api.py, "
            "or use api_key_override."
        )

    return key


def _resolution_to_api(resolution):
    try:
        return RESOLUTION_API[resolution]
    except KeyError as exc:
        raise ValueError(f"Unsupported FLUX 3 resolution: {resolution}") from exc


def _duration_to_api(duration, max_seconds=20):
    if duration == "auto":
        return "auto"

    seconds = int(duration)

    if seconds < 5 or seconds > max_seconds:
        raise ValueError(
            f"FLUX 3 duration must be 5-{max_seconds} seconds for this mode."
        )

    return seconds


def _estimate_cost(mode, duration, resolution, draft):
    if draft:
        rate = DRAFT_CREDITS_PER_SECOND[mode]
        effective_resolution = "720p"
    else:
        rate = DIRECT_CREDITS_PER_SECOND[mode][resolution]
        effective_resolution = resolution

    if duration == "auto":
        return {
            "credits": None,
            "credits_per_second": rate,
            "usd": None,
            "usd_per_second": rate / 100.0,
            "resolution": effective_resolution,
        }

    seconds = int(duration)
    credits = rate * seconds

    return {
        "credits": credits,
        "credits_per_second": rate,
        "usd": credits / 100.0,
        "usd_per_second": rate / 100.0,
        "resolution": effective_resolution,
    }


def _estimate_text(mode, duration, resolution, draft):
    estimate = _estimate_cost(mode, duration, resolution, draft)

    if estimate["credits"] is None:
        return (
            f"Estimated direct BFL price: "
            f"{estimate['credits_per_second']:.0f} credits/s "
            f"(${estimate['usd_per_second']:.2f}/s)"
        )

    return (
        f"Estimated direct BFL price: "
        f"{estimate['credits']:.0f} credits "
        f"(${estimate['usd']:.2f})"
    )


def _validate_prompt(prompt):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("FLUX 3 requires a non-empty prompt.")


def _validate_image_tensor(image):
    if image is None:
        raise ValueError("Image is missing.")

    if not isinstance(image, torch.Tensor):
        raise TypeError("FLUX 3 keyframes must be ComfyUI IMAGE tensors.")

    # Comfy IMAGE is usually [B, H, W, C].
    if image.ndim == 4:
        height = int(image.shape[1])
        width = int(image.shape[2])
    elif image.ndim == 3:
        height = int(image.shape[0])
        width = int(image.shape[1])
    else:
        raise ValueError(f"Unexpected IMAGE tensor shape: {tuple(image.shape)}")

    if width < MIN_IMAGE_SIDE or height < MIN_IMAGE_SIDE:
        raise ValueError(
            f"FLUX 3 keyframes must be at least "
            f"{MIN_IMAGE_SIDE}x{MIN_IMAGE_SIDE}px; got {width}x{height}."
        )

    aspect = max(width, height) / max(1, min(width, height))

    if aspect > MAX_IMAGE_ASPECT:
        raise ValueError(
            f"FLUX 3 keyframe aspect ratio is too extreme: "
            f"{width}x{height}. Maximum is {MAX_IMAGE_ASPECT:g}:1."
        )


def _image_to_data_url(image):
    _validate_image_tensor(image)

    if image.ndim == 4:
        image = image[0]

    image_np = image.detach().cpu().numpy()
    image_np = np.clip(image_np, 0.0, 1.0)

    pil_image = Image.fromarray((image_np * 255).astype(np.uint8))

    buffer = BytesIO()
    pil_image.save(buffer, format="PNG")

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _flatten_image_inputs(*images):
    flat = []

    for tensor in images:
        if tensor is None:
            continue

        if not isinstance(tensor, torch.Tensor):
            raise TypeError("FLUX 3 keyframes must be IMAGE tensors.")

        if tensor.ndim == 4:
            for i in range(tensor.shape[0]):
                flat.append(tensor[i])
        else:
            flat.append(tensor)

    if len(flat) > MAX_KEYFRAMES:
        raise ValueError(
            f"FLUX 3 supports at most {MAX_KEYFRAMES} keyframe images; "
            f"got {len(flat)}."
        )

    for tensor in flat:
        _validate_image_tensor(tensor)

    return flat


def _parse_times(value, image_count, duration):
    parts = [part.strip() for part in (value or "").split(",") if part.strip()]

    if len(parts) != image_count:
        raise ValueError(
            f"Give one keyframe time per image. "
            f"Got {len(parts)} time(s) for {image_count} image(s). "
            f"Example: 0, 2.5, 5"
        )

    try:
        times = [float(part) for part in parts]
    except ValueError as exc:
        raise ValueError(
            "Keyframe times must be numbers in seconds, comma-separated."
        ) from exc

    if not all(math.isfinite(t) for t in times):
        raise ValueError("Keyframe times must be finite numbers.")

    if times[0] < 0:
        raise ValueError("Keyframe times cannot be negative.")

    if any(later <= earlier for earlier, later in zip(times, times[1:])):
        raise ValueError(
            f"Keyframe times must be strictly increasing; got {times}."
        )

    cap = 20 if duration == "auto" else int(duration)

    if times[-1] > cap:
        raise ValueError(
            f"Last keyframe is at {times[-1]}s, "
            f"past the end of the {cap}s clip."
        )

    return times


def _video_to_data_url(video):
    if video is None:
        raise ValueError("FLUX 3 Video Continuation requires a VIDEO input.")

    # Prefer saving through ComfyUI's VideoInput interface. This also respects
    # trims for video implementations that provide them.
    buffer = BytesIO()

    try:
        video.save_to(buffer)
        data = buffer.getvalue()
    except Exception:
        # Fallback for VideoFromFile / compatible objects.
        if not hasattr(video, "get_stream_source"):
            raise

        source = video.get_stream_source()

        if isinstance(source, BytesIO):
            source.seek(0)
            data = source.read()
            source.seek(0)
        elif isinstance(source, bytes):
            data = source
        else:
            with open(source, "rb") as f:
                data = f.read()

    container = "mp4"

    try:
        fmt = (video.get_container_format() or "").lower()
        if "webm" in fmt:
            container = "webm"
    except Exception:
        pass

    mime = "video/webm" if container == "webm" else "video/mp4"
    encoded = base64.b64encode(data).decode("ascii")

    return f"data:{mime};base64,{encoded}"


def _download_video(url):
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise Exception(f"Could not download FLUX 3 result video: {exc}") from exc

    return VideoFromFile(BytesIO(response.content))


def _download_draft_cache_as_base64(url, api_key):
    if not url:
        raise ValueError("Draft cache URL is empty.")

    headers = {"x-key": api_key}

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        # Signed delivery URLs normally do not require the x-key.
        if response.status_code in {401, 403}:
            response = requests.get(
                url,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

        response.raise_for_status()
    except requests.RequestException as exc:
        raise Exception(f"Could not download FLUX 3 draft cache: {exc}") from exc

    return base64.b64encode(response.content).decode("ascii")


def _submit_and_poll(payload, api_key, estimate_text=None):
    headers = {
        "x-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if estimate_text:
        print(f"[BFL] FLUX 3 — {estimate_text}")

    try:
        response = requests.post(
            FLUX3_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise Exception(f"FLUX 3 connection error: {exc}") from exc

    if not response.ok:
        raise Exception(_format_http_error(response))

    try:
        submit = response.json()
    except ValueError as exc:
        raise Exception("FLUX 3 submit response was not valid JSON.") from exc

    polling_url = submit.get("polling_url")

    if not polling_url:
        raise Exception(
            f"FLUX 3 response did not contain polling_url: {submit}"
        )

    exact_cost = submit.get("cost")

    if exact_cost is not None:
        exact_cost = float(exact_cost)
        print(
            f"[BFL] FLUX 3 exact request cost: "
            f"{exact_cost:g} credits (${exact_cost / 100.0:.2f})"
        )

    started = time.time()
    consecutive_retryable_errors = 0

    while True:
        if time.time() - started > GENERATION_TIMEOUT_SECONDS:
            raise Exception(
                "FLUX 3 generation timed out after "
                f"{GENERATION_TIMEOUT_SECONDS} seconds."
            )

        time.sleep(POLL_INTERVAL_SECONDS)

        try:
            poll_response = requests.get(
                polling_url,
                headers={"x-key": api_key, "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            consecutive_retryable_errors += 1

            if consecutive_retryable_errors <= MAX_POLL_RETRIES:
                continue

            raise Exception(f"FLUX 3 polling error: {exc}") from exc

        if poll_response.status_code >= 500:
            consecutive_retryable_errors += 1

            if consecutive_retryable_errors <= MAX_POLL_RETRIES:
                continue

        else:
            consecutive_retryable_errors = 0

        if not poll_response.ok:
            raise Exception(_format_http_error(poll_response))

        try:
            result = poll_response.json()
        except ValueError as exc:
            raise Exception(
                "FLUX 3 polling response was not valid JSON."
            ) from exc

        status = result.get("status")

        if status == "Ready":
            result_data = result.get("result") or {}
            sample_url = result_data.get("sample")

            if not sample_url:
                raise Exception(
                    f"FLUX 3 returned Ready without result.sample: {result}"
                )

            video = _download_video(sample_url)
            draft_cache_url = result_data.get("draft_cache") or ""

            if exact_cost is None:
                cost_text = "BFL cost: exact cost was not returned by the API."
            else:
                cost_text = (
                    f"BFL cost: {exact_cost:g} credits "
                    f"(${exact_cost / 100.0:.2f})"
                )

            return video, str(draft_cache_url), cost_text, exact_cost

        if status in {
            "Error",
            "Request Moderated",
            "Content Moderated",
            "Task not found",
        }:
            raise Exception(f"FLUX 3 generation failed: {result}")


class Flux3NodeBase:
    RETURN_TYPES = ("VIDEO", "STRING")
    RETURN_NAMES = ("VIDEO", "draft_cache_url")
    FUNCTION = "generate"
    CATEGORY = "Flux/FLUX 3"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # FLUX 3 is nondeterministic and API state is external.
        return float("NaN")

    @staticmethod
    def _common_payload(
        prompt,
        aspect_ratio,
        duration,
        resolution,
        generate_audio,
        safety_tolerance,
        draft,
        max_duration=20,
    ):
        _validate_prompt(prompt)

        api_resolution = _resolution_to_api(resolution)

        # BFL documents draft output as HD.
        if draft:
            api_resolution = "hd"

        return {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": _duration_to_api(duration, max_seconds=max_duration),
            "resolution": api_resolution,
            "version": "latest",
            "generate_audio": bool(generate_audio),
            "safety_tolerance": int(safety_tolerance),
            "draft": bool(draft),
        }

    @staticmethod
    def _result(video, draft_cache_url, cost_text, exact_cost=None):
        ui = {
            "text": [cost_text],
        }

        if exact_cost is not None:
            ui["bfl_cost"] = [float(exact_cost)]

        return {
            "ui": ui,
            "result": (
                video,
                draft_cache_url,
            ),
        }


class Flux3TextToVideo(Flux3NodeBase):
    DESCRIPTION = (
        "Generates video with synchronized audio from text. "
        "Direct pricing: 17 credits/s at 720p or 29 credits/s at 1080p. "
        "Draft: 6 credits/s (HD). 1 credit = $0.01."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                    },
                ),
                "aspect_ratio": (
                    ASPECT_RATIOS,
                    {"default": "auto"},
                ),
                "duration": (
                    DURATIONS_5_20,
                    {"default": "auto"},
                ),
                "resolution": (
                    RESOLUTIONS,
                    {"default": "720p"},
                ),
                "generate_audio": (
                    "BOOLEAN",
                    {"default": True},
                ),
                "safety_tolerance": (
                    "INT",
                    {
                        "default": 2,
                        "min": 0,
                        "max": 4,
                        "step": 1,
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 42,
                        "min": 0,
                        "max": 0xFFFFFFFF,
                    },
                ),
            },
            "optional": {
                "draft": (
                    "BOOLEAN",
                    {"default": False},
                ),
                "api_key_override": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "",
                    },
                ),
            },
        }

    def generate(
        self,
        prompt,
        aspect_ratio,
        duration,
        resolution,
        generate_audio,
        safety_tolerance,
        seed,
        draft=False,
        api_key_override="",
    ):
        api_key = _require_api_key(api_key_override)

        payload = self._common_payload(
            prompt,
            aspect_ratio,
            duration,
            resolution,
            generate_audio,
            safety_tolerance,
            draft,
        )
        payload["mode"] = "t2v"

        estimate = _estimate_text(
            "t2v",
            duration,
            resolution,
            draft,
        )

        video, cache, cost_text, exact_cost = _submit_and_poll(
            payload,
            api_key,
            estimate_text=estimate,
        )

        return self._result(video, cache, cost_text, exact_cost)


class Flux3ImageToVideo(Flux3NodeBase):
    DESCRIPTION = (
        "Animates 1-10 images. One image opens the clip; "
        "two images become start/end; more can be spread through the clip "
        "or pinned to exact times. Direct pricing: 17 credits/s at 720p "
        "or 29 credits/s at 1080p. Draft: 6 credits/s (HD)."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # Required on purpose: this prevents the ambiguous None input
                # that the previous all-in-one node could receive.
                "image_0": (
                    "IMAGE",
                    {
                        "tooltip": (
                            "Connect the IMAGE output of Load Image here. "
                            "Load Image must be set to Mode → Always, not Bypass."
                        ),
                    },
                ),
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                    },
                ),
                "placement": (
                    ["spread across the clip", "at times"],
                    {"default": "spread across the clip"},
                ),
                "aspect_ratio": (
                    ASPECT_RATIOS,
                    {"default": "auto"},
                ),
                "duration": (
                    DURATIONS_5_20,
                    {"default": "auto"},
                ),
                "resolution": (
                    RESOLUTIONS,
                    {"default": "720p"},
                ),
                "generate_audio": (
                    "BOOLEAN",
                    {"default": True},
                ),
                "safety_tolerance": (
                    "INT",
                    {
                        "default": 2,
                        "min": 0,
                        "max": 2,
                        "step": 1,
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 42,
                        "min": 0,
                        "max": 0xFFFFFFFF,
                    },
                ),
            },
            "optional": {
                "image_1": ("IMAGE",),
                "image_2": ("IMAGE",),
                "image_3": ("IMAGE",),
                "image_4": ("IMAGE",),
                "image_5": ("IMAGE",),
                "image_6": ("IMAGE",),
                "image_7": ("IMAGE",),
                "image_8": ("IMAGE",),
                "image_9": ("IMAGE",),
                "times": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "0",
                    },
                ),
                "draft": (
                    "BOOLEAN",
                    {"default": False},
                ),
                "api_key_override": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "",
                    },
                ),
            },
        }

    def generate(
        self,
        image_0,
        prompt,
        placement,
        aspect_ratio,
        duration,
        resolution,
        generate_audio,
        safety_tolerance,
        seed,
        image_1=None,
        image_2=None,
        image_3=None,
        image_4=None,
        image_5=None,
        image_6=None,
        image_7=None,
        image_8=None,
        image_9=None,
        times="0",
        draft=False,
        api_key_override="",
    ):
        api_key = _require_api_key(api_key_override)

        payload = self._common_payload(
            prompt,
            aspect_ratio,
            duration,
            resolution,
            generate_audio,
            min(int(safety_tolerance), 2),
            draft,
        )
        payload["mode"] = "i2v"

        images = _flatten_image_inputs(
            image_0,
            image_1,
            image_2,
            image_3,
            image_4,
            image_5,
            image_6,
            image_7,
            image_8,
            image_9,
        )

        if not images:
            raise ValueError(
                "Connect at least one keyframe image. "
                "If a Load Image node is connected but this error appears, "
                "make sure that Load Image is set to Mode → Always and is not bypassed."
            )

        encoded = [_image_to_data_url(image) for image in images]

        if placement == "at times":
            parsed_times = _parse_times(
                times,
                len(encoded),
                duration,
            )
            payload["keyframes"] = [
                [timestamp, image]
                for timestamp, image in zip(parsed_times, encoded)
            ]

        else:
            if len(encoded) >= 3 and duration == "auto":
                raise ValueError(
                    f"Spreading {len(encoded)} images across the clip needs "
                    f"an explicit duration. Set duration, or choose 'at times'."
                )

            # Match BFL's documented semantics:
            # one keyframe = exact opening frame;
            # two = start/end;
            # multiple = ordered storyboard.
            payload["keyframes"] = (
                encoded[0]
                if len(encoded) == 1
                else encoded
            )

        estimate = _estimate_text(
            "i2v",
            duration,
            resolution,
            draft,
        )

        video, cache, cost_text, exact_cost = _submit_and_poll(
            payload,
            api_key,
            estimate_text=estimate,
        )

        return self._result(video, cache, cost_text, exact_cost)


class Flux3VideoContinuation(Flux3NodeBase):
    DESCRIPTION = (
        "Continues an existing video. "
        "Direct pricing: 43 credits/s at 720p or 54 credits/s at 1080p. "
        "Draft: 12 credits/s (HD). Output length is 5-15 seconds."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                    },
                ),
                "aspect_ratio": (
                    ASPECT_RATIOS,
                    {"default": "auto"},
                ),
                "duration": (
                    DURATIONS_5_15,
                    {"default": "auto"},
                ),
                "resolution": (
                    RESOLUTIONS,
                    {"default": "720p"},
                ),
                "generate_audio": (
                    "BOOLEAN",
                    {"default": True},
                ),
                "safety_tolerance": (
                    "INT",
                    {
                        "default": 2,
                        "min": 0,
                        "max": 2,
                        "step": 1,
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 42,
                        "min": 0,
                        "max": 0xFFFFFFFF,
                    },
                ),
            },
            "optional": {
                "draft": (
                    "BOOLEAN",
                    {"default": False},
                ),
                "api_key_override": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "",
                    },
                ),
            },
        }

    def generate(
        self,
        video,
        prompt,
        aspect_ratio,
        duration,
        resolution,
        generate_audio,
        safety_tolerance,
        seed,
        draft=False,
        api_key_override="",
    ):
        api_key = _require_api_key(api_key_override)

        payload = self._common_payload(
            prompt,
            aspect_ratio,
            duration,
            resolution,
            generate_audio,
            min(int(safety_tolerance), 2),
            draft,
            max_duration=15,
        )
        payload["mode"] = "v2v"
        payload["start_video"] = _video_to_data_url(video)

        estimate = _estimate_text(
            "v2v",
            duration,
            resolution,
            draft,
        )

        video_out, cache, cost_text, exact_cost = _submit_and_poll(
            payload,
            api_key,
            estimate_text=estimate,
        )

        return self._result(video_out, cache, cost_text, exact_cost)


class Flux3DraftEnhance:
    DESCRIPTION = (
        "Renders a selected FLUX 3 draft at full quality "
        "without reinterpreting the shot. Connect draft_cache_url from a "
        "draft Text-to-Video, Image-to-Video or Video Continuation node. "
        "BFL does not currently publish a separate fixed per-second rate for "
        "draft_enhance; the exact charged credits are read from the API response."
    )

    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("VIDEO",)
    FUNCTION = "enhance"
    CATEGORY = "Flux/FLUX 3"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "draft_cache_url": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "",
                    },
                ),
            },
            "optional": {
                "api_key_override": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "",
                    },
                ),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")

    def enhance(
        self,
        draft_cache_url,
        api_key_override="",
    ):
        api_key = _require_api_key(api_key_override)

        draft_cache_b64 = _download_draft_cache_as_base64(
            draft_cache_url,
            api_key,
        )

        payload = {
            "mode": "draft_enhance",
            "draft_cache": draft_cache_b64,
        }

        video, _cache, cost_text, exact_cost = _submit_and_poll(
            payload,
            api_key,
            estimate_text=(
                "Draft Enhance: exact price will be taken from "
                "the BFL submit response"
            ),
        )

        ui = {
            "text": [cost_text],
        }

        if exact_cost is not None:
            ui["bfl_cost"] = [float(exact_cost)]

        return {
            "ui": ui,
            "result": (video,),
        }

class Flux3VideoLegacy(Flux3NodeBase):
    DEPRECATED = True
    """
    Compatibility node for workflows created with the first version of this fork.

    New workflows should use the dedicated T2V / I2V / V2V nodes above.
    """

    DESCRIPTION = (
        "Legacy compatibility node. Prefer the dedicated FLUX 3 Text to Video, "
        "Image to Video, and Video Continuation nodes."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (
                    ["t2v", "i2v", "v2v"],
                    {"default": "t2v"},
                ),
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                    },
                ),
                "aspect_ratio": (
                    ASPECT_RATIOS,
                    {"default": "auto"},
                ),
                "duration": (
                    DURATIONS_5_20,
                    {"default": "auto"},
                ),
                "resolution": (
                    ["hd", "fhd", "720p", "1080p"],
                    {"default": "hd"},
                ),
                "generate_audio": (
                    "BOOLEAN",
                    {"default": True},
                ),
                "safety_tolerance": (
                    "INT",
                    {
                        "default": 2,
                        "min": 0,
                        "max": 4,
                        "step": 1,
                    },
                ),
                "draft": (
                    "BOOLEAN",
                    {"default": False},
                ),
            },
            "optional": {
                "start_image": ("IMAGE",),
                "end_image": ("IMAGE",),
                "start_video": ("VIDEO",),
                "draft_cache_url": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "",
                    },
                ),
                "api_key_override": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "",
                    },
                ),
            },
        }

    def generate(
        self,
        mode,
        prompt,
        aspect_ratio,
        duration,
        resolution,
        generate_audio,
        safety_tolerance,
        draft,
        start_image=None,
        end_image=None,
        start_video=None,
        draft_cache_url="",
        api_key_override="",
    ):
        ui_resolution = (
            "1080p"
            if resolution in {"fhd", "1080p"}
            else "720p"
        )

        if mode == "t2v":
            return Flux3TextToVideo().generate(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                duration=duration,
                resolution=ui_resolution,
                generate_audio=generate_audio,
                safety_tolerance=safety_tolerance,
                seed=42,
                draft=draft,
                api_key_override=api_key_override,
            )

        if mode == "i2v":
            if start_image is None:
                raise ValueError(
                    "No start image reached FLUX 3. "
                    "Your workflow may show a cable, but the upstream Load Image "
                    "node can still be bypassed. Set Load Image to Mode → Always. "
                    "For new workflows use 'FLUX 3 Image to Video'."
                )

            return Flux3ImageToVideo().generate(
                image_0=start_image,
                image_1=end_image,
                prompt=prompt,
                placement="spread across the clip",
                aspect_ratio=aspect_ratio,
                duration=duration,
                resolution=ui_resolution,
                generate_audio=generate_audio,
                safety_tolerance=min(int(safety_tolerance), 2),
                seed=42,
                times="0",
                draft=draft,
                api_key_override=api_key_override,
            )

        if mode == "v2v":
            if start_video is None:
                raise ValueError(
                    "No VIDEO input reached FLUX 3 Video Continuation."
                )

            if duration != "auto" and int(duration) > 15:
                raise ValueError(
                    "FLUX 3 Video Continuation supports at most 15 seconds."
                )

            return Flux3VideoContinuation().generate(
                video=start_video,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                duration=duration,
                resolution=ui_resolution,
                generate_audio=generate_audio,
                safety_tolerance=min(int(safety_tolerance), 2),
                seed=42,
                draft=draft,
                api_key_override=api_key_override,
            )

        raise ValueError(f"Unsupported legacy FLUX 3 mode: {mode}")
