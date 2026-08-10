import base64
import os
import time
from io import BytesIO

import numpy as np
import requests
import torch
from PIL import Image


# Current BFL API entry points.
# EU1 / US1 are kept as aliases so existing ComfyUI workflows continue to load.
API_ROOTS = {
    "Global": "https://api.bfl.ai/",
    "EU": "https://api.eu.bfl.ai/",
    "US": "https://api.us.bfl.ai/",
    "EU1": "https://api.eu.bfl.ai/",
    "US1": "https://api.us.bfl.ai/",
}

DEFAULT_REGION = "EU"

REQUEST_TIMEOUT_SECONDS = 60
GENERATION_TIMEOUT_SECONDS = 300
POLL_INTERVAL_SECONDS = 0.5


def get_api_key():
    api_key = os.environ.get("BFL_API_KEY")
    if api_key:
        return api_key.strip()

    dir_path = os.path.dirname(os.path.realpath(__file__))
    key_file_path = os.path.join(dir_path, "bfl_api_key.txt")

    if os.path.exists(key_file_path):
        with open(key_file_path, "r", encoding="utf-8") as f:
            api_key = f.read().strip()
            if api_key:
                return api_key

    return None


class FluxBase:
    API_ENDPOINT = ""
    POLL_ENDPOINT = "v1/get_result"
    ACCEPT = "application/json"
    INPUT_SPEC = {}
    CATEGORY = "Flux"

    @classmethod
    def INPUT_TYPES(cls):
        required = dict(cls.INPUT_SPEC.get("required", {}))
        optional = dict(cls.INPUT_SPEC.get("optional", {}))

        optional["region"] = (
            ["Global", "EU", "US", "EU1", "US1"],
            {"default": DEFAULT_REGION},
        )

        return {
            "required": required,
            "optional": optional,
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "call"

    def call(self, *args, **kwargs):
        region = kwargs.get("region", DEFAULT_REGION)
        api_key_override = kwargs.get("api_key_override")
        api_key = api_key_override or get_api_key()

        if not api_key:
            raise Exception(
                "No Black Forest Labs API key set. "
                "Set environment variable BFL_API_KEY, create bfl_api_key.txt "
                "next to bfl_api.py, or use api_key_override."
            )

        data = {
            key: value
            for key, value in kwargs.items()
            if key not in {"region", "api_key_override"} and value is not None
        }

        self._prepare_payload(data)

        headers = {
            "Accept": self.ACCEPT or "application/json",
            "Content-Type": "application/json",
            "x-key": api_key,
        }

        response = self._make_request(
            headers=headers,
            data=data,
            region=region,
        )

        if not response.ok:
            raise Exception(self._format_api_error(response))

        return self._handle_response(
            response=response,
            headers=headers,
            region=region,
        )

    def _prepare_payload(self, data):
        """Hook for subclasses to convert images or rename API fields."""
        return

    def _get_base_url(self, region):
        return API_ROOTS.get(region, API_ROOTS[DEFAULT_REGION])

    def _make_request(self, headers, data, region):
        base_url = self._get_base_url(region)
        url = f"{base_url}{self.API_ENDPOINT}"

        try:
            return requests.post(
                url,
                headers=headers,
                json=data,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise Exception(f"BFL API connection error: {exc}") from exc

    def _handle_response(self, response, headers, region=DEFAULT_REGION):
        # Some older endpoints could theoretically return an image directly.
        content_type = response.headers.get("Content-Type", "")
        if content_type.startswith("image/"):
            return self._process_image_response(response)

        try:
            result = response.json()
        except ValueError as exc:
            raise Exception(
                f"BFL API returned invalid JSON "
                f"(HTTP {response.status_code}): {response.text[:500]}"
            ) from exc

        # Current BFL APIs return an absolute polling_url.
        polling_url = result.get("polling_url")
        if polling_url:
            return self._poll_for_result(
                polling_url=polling_url,
                headers=headers,
                region=region,
                task_id=result.get("id"),
            )

        # Backward compatibility for endpoints that only return an id.
        task_id = result.get("id")
        if task_id and self.POLL_ENDPOINT:
            return self._poll_for_result(
                polling_url=None,
                headers=headers,
                region=region,
                task_id=task_id,
            )

        # If the endpoint ever returns a completed result immediately.
        if result.get("status") == "Ready":
            return self._ready_result_to_image(result)

        raise Exception(
            f"BFL API response contained neither polling_url nor task id: {result}"
        )

    def _poll_for_result(
        self,
        polling_url,
        headers,
        region=DEFAULT_REGION,
        task_id=None,
    ):
        start_time = time.time()

        while True:
            if time.time() - start_time > GENERATION_TIMEOUT_SECONDS:
                raise Exception(
                    "BFL API Timeout: generation took longer than "
                    f"{GENERATION_TIMEOUT_SECONDS} seconds."
                )

            if polling_url:
                url = polling_url
                params = None
            else:
                if not task_id:
                    raise Exception("BFL API Error: missing polling URL and task id.")
                base_url = self._get_base_url(region)
                url = f"{base_url}{self.POLL_ENDPOINT}"
                params = {"id": task_id}

            try:
                response = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            except requests.RequestException as exc:
                raise Exception(f"BFL API polling error: {exc}") from exc

            # Older BFL endpoints may briefly return 202 while processing.
            if response.status_code == 202:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            if response.status_code == 404:
                raise Exception(
                    "BFL API Error: generation task was not found "
                    f"(HTTP 404): {response.text[:500]}"
                )

            if not response.ok:
                raise Exception(self._format_api_error(response))

            try:
                result = response.json()
            except ValueError as exc:
                raise Exception(
                    f"BFL polling returned invalid JSON "
                    f"(HTTP {response.status_code}): {response.text[:500]}"
                ) from exc

            status = result.get("status")

            if status == "Ready":
                return self._ready_result_to_image(result)

            if status in {
                "Error",
                "Failed",
                "Request Moderated",
                "Content Moderated",
            }:
                raise Exception(f"BFL API generation failed: {result}")

            # Pending / Processing / Generating / InProgress / etc.
            time.sleep(POLL_INTERVAL_SECONDS)

    def _ready_result_to_image(self, result):
        result_data = result.get("result") or {}

        # "sample" is the standard BFL image result field.
        image_url = (
            result_data.get("sample")
            or result_data.get("url")
            or result_data.get("image")
        )

        if not image_url:
            raise Exception(
                f"BFL API returned status Ready without an image URL: {result}"
            )

        try:
            image_response = requests.get(
                image_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            image_response.raise_for_status()
        except requests.RequestException as exc:
            raise Exception(
                f"Could not download BFL result image: {exc}"
            ) from exc

        return self._process_image_response(image_response)

    def _process_image_response(self, response):
        try:
            image = Image.open(BytesIO(response.content)).convert("RGBA")
        except Exception as exc:
            raise Exception(
                "BFL result could not be decoded as an image."
            ) from exc

        image_array = np.array(image).astype(np.float32) / 255.0
        return (torch.from_numpy(image_array)[None,],)

    def _convert_image_to_base64(self, image):
        if isinstance(image, torch.Tensor):
            image_np = image[0].detach().cpu().numpy()
            image_np = np.clip(image_np, 0.0, 1.0)

            pil_image = Image.fromarray(
                (image_np * 255).astype(np.uint8)
            )

            buffered = BytesIO()
            pil_image.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode("ascii")

        return image

    def _convert_mask_to_base64(self, mask):
        if isinstance(mask, torch.Tensor):
            mask_np = mask.detach().cpu().numpy()

            if len(mask_np.shape) == 3:
                mask_np = mask_np[0]

            mask_np = np.clip(mask_np, 0.0, 1.0)

            pil_mask = Image.fromarray(
                (mask_np * 255).astype(np.uint8),
                mode="L",
            )

            buffered = BytesIO()
            pil_mask.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode("ascii")

        return mask

    @staticmethod
    def _format_api_error(response):
        try:
            detail = response.json()
        except ValueError:
            detail = response.text

        return (
            f"BFL API Error HTTP {response.status_code}: {detail}"
        )


# ---------------------------------------------------------------------------
# FLUX 1.x legacy nodes
# ---------------------------------------------------------------------------


class FluxPro(FluxBase):
    API_ENDPOINT = "v1/flux-pro"
    INPUT_SPEC = {
        "required": {
            "prompt": ("STRING", {"multiline": True}),
        },
        "optional": {
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "guidance": (
                "FLOAT",
                {
                    "default": 2.5,
                    "min": 1.5,
                    "max": 5,
                    "step": 0.01,
                },
            ),
            "width": (
                "INT",
                {
                    "default": 1024,
                    "min": 0,
                    "max": 1440,
                    "step": 32,
                },
            ),
            "height": (
                "INT",
                {
                    "default": 1024,
                    "min": 0,
                    "max": 1440,
                    "step": 32,
                },
            ),
            "steps": (
                "INT",
                {"default": 50, "min": 10, "max": 100},
            ),
            "interval": (
                "INT",
                {"default": 1, "min": 1, "max": 10},
            ),
            "prompt_upsampling": (
                "BOOLEAN",
                {
                    "default": True,
                    "label_on": "True",
                    "label_off": "False",
                },
            ),
            "safety_tolerance": (
                "INT",
                {"default": 2, "min": 0, "max": 6},
            ),
            "api_key_override": (
                "STRING",
                {"multiline": False},
            ),
            "image_prompt": ("IMAGE",),
        },
    }

    def _prepare_payload(self, data):
        if data.get("image_prompt") is not None:
            data["image_prompt"] = self._convert_image_to_base64(
                data["image_prompt"]
            )


class FluxDev(FluxBase):
    API_ENDPOINT = "v1/flux-dev"
    INPUT_SPEC = {
        "required": {
            "prompt": ("STRING", {"multiline": True}),
        },
        "optional": {
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "guidance": (
                "FLOAT",
                {
                    "default": 2.5,
                    "min": 1.5,
                    "max": 5,
                    "step": 0.01,
                },
            ),
            "width": (
                "INT",
                {
                    "default": 1024,
                    "min": 0,
                    "max": 1440,
                    "step": 32,
                },
            ),
            "height": (
                "INT",
                {
                    "default": 1024,
                    "min": 0,
                    "max": 1440,
                    "step": 32,
                },
            ),
            "steps": (
                "INT",
                {"default": 50, "min": 10, "max": 100},
            ),
            "interval": (
                "INT",
                {"default": 1, "min": 1, "max": 10},
            ),
            "prompt_upsampling": (
                "BOOLEAN",
                {
                    "default": True,
                    "label_on": "True",
                    "label_off": "False",
                },
            ),
            "safety_tolerance": (
                "INT",
                {"default": 2, "min": 0, "max": 6},
            ),
            "api_key_override": (
                "STRING",
                {"multiline": False},
            ),
            "image_prompt": ("IMAGE",),
        },
    }

    def _prepare_payload(self, data):
        if data.get("image_prompt") is not None:
            data["image_prompt"] = self._convert_image_to_base64(
                data["image_prompt"]
            )


class FluxPro11(FluxBase):
    API_ENDPOINT = "v1/flux-pro-1.1"
    INPUT_SPEC = {
        "required": {
            "prompt": ("STRING", {"multiline": True}),
        },
        "optional": {
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "guidance": (
                "FLOAT",
                {
                    "default": 2.5,
                    "min": 1.5,
                    "max": 5,
                    "step": 0.01,
                },
            ),
            "width": (
                "INT",
                {
                    "default": 1024,
                    "min": 0,
                    "max": 1440,
                    "step": 32,
                },
            ),
            "height": (
                "INT",
                {
                    "default": 1024,
                    "min": 0,
                    "max": 1440,
                    "step": 32,
                },
            ),
            "interval": (
                "INT",
                {"default": 1, "min": 1, "max": 10},
            ),
            "prompt_upsampling": (
                "BOOLEAN",
                {
                    "default": True,
                    "label_on": "True",
                    "label_off": "False",
                },
            ),
            "safety_tolerance": (
                "INT",
                {"default": 2, "min": 0, "max": 6},
            ),
            "api_key_override": (
                "STRING",
                {"multiline": False},
            ),
            "image_prompt": ("IMAGE",),
        },
    }

    def _prepare_payload(self, data):
        if data.get("image_prompt") is not None:
            data["image_prompt"] = self._convert_image_to_base64(
                data["image_prompt"]
            )


class FluxProFill(FluxBase):
    API_ENDPOINT = "v1/flux-pro-1.0-fill"
    INPUT_SPEC = {
        "required": {
            "image": ("IMAGE",),
            "prompt": ("STRING", {"multiline": True}),
        },
        "optional": {
            "mask": ("MASK",),
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "guidance": (
                "FLOAT",
                {
                    "default": 60.0,
                    "min": 1.5,
                    "max": 100,
                    "step": 0.1,
                },
            ),
            "steps": (
                "INT",
                {"default": 50, "min": 15, "max": 50},
            ),
            "prompt_upsampling": (
                "BOOLEAN",
                {"default": False},
            ),
            "safety_tolerance": (
                "INT",
                {"default": 2, "min": 0, "max": 6},
            ),
            "api_key_override": (
                "STRING",
                {"multiline": False},
            ),
        },
    }

    def _prepare_payload(self, data):
        if data.get("image") is not None:
            data["image"] = self._convert_image_to_base64(
                data["image"]
            )

        if data.get("mask") is not None:
            data["mask"] = self._convert_mask_to_base64(
                data["mask"]
            )


class FluxCanny(FluxBase):
    API_ENDPOINT = "v1/flux-pro-1.0-canny"
    INPUT_SPEC = {
        "required": {
            "prompt": ("STRING", {"multiline": True}),
            "control_image": ("IMAGE",),
        },
        "optional": {
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "guidance": (
                "FLOAT",
                {
                    "default": 30.0,
                    "min": 1.0,
                    "max": 100,
                    "step": 0.1,
                },
            ),
            "steps": (
                "INT",
                {"default": 50, "min": 15, "max": 50},
            ),
            "low_threshold": (
                "INT",
                {"default": 50, "min": 0, "max": 500},
            ),
            "high_threshold": (
                "INT",
                {"default": 200, "min": 0, "max": 500},
            ),
            "prompt_upsampling": (
                "BOOLEAN",
                {"default": False},
            ),
            "safety_tolerance": (
                "INT",
                {"default": 2, "min": 0, "max": 6},
            ),
            "api_key_override": (
                "STRING",
                {"multiline": False},
            ),
        },
    }

    def _prepare_payload(self, data):
        if data.get("control_image") is not None:
            data["control_image"] = self._convert_image_to_base64(
                data["control_image"]
            )

        if "low_threshold" in data:
            data["canny_low_threshold"] = int(
                data.pop("low_threshold")
            )

        if "high_threshold" in data:
            data["canny_high_threshold"] = int(
                data.pop("high_threshold")
            )


class FluxDepth(FluxBase):
    API_ENDPOINT = "v1/flux-pro-1.0-depth"
    INPUT_SPEC = {
        "required": {
            "prompt": ("STRING", {"multiline": True}),
            "control_image": ("IMAGE",),
        },
        "optional": {
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "guidance": (
                "FLOAT",
                {
                    "default": 15.0,
                    "min": 1.0,
                    "max": 100,
                    "step": 0.1,
                },
            ),
            "steps": (
                "INT",
                {"default": 50, "min": 15, "max": 50},
            ),
            "prompt_upsampling": (
                "BOOLEAN",
                {"default": False},
            ),
            "safety_tolerance": (
                "INT",
                {"default": 2, "min": 0, "max": 6},
            ),
            "api_key_override": (
                "STRING",
                {"multiline": False},
            ),
        },
    }

    def _prepare_payload(self, data):
        if data.get("control_image") is not None:
            data["control_image"] = self._convert_image_to_base64(
                data["control_image"]
            )


class FluxUltra11(FluxBase):
    API_ENDPOINT = "v1/flux-pro-1.1-ultra"
    INPUT_SPEC = {
        "required": {
            "prompt": ("STRING", {"multiline": True}),
        },
        "optional": {
            "image_prompt": ("IMAGE",),
            "aspect_ratio": (
                "STRING",
                {"default": "1:1"},
            ),
            "raw": (
                "BOOLEAN",
                {
                    "default": False,
                    "label_on": "True",
                    "label_off": "False",
                },
            ),
            "safety_tolerance": (
                "INT",
                {
                    "default": 5,
                    "min": 1,
                    "max": 5,
                    "step": 1,
                },
            ),
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "image_prompt_strength": (
                "FLOAT",
                {
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                },
            ),
            "output_format": (
                "STRING",
                {"default": "png"},
            ),
            "api_key_override": (
                "STRING",
                {"multiline": False},
            ),
        },
    }

    def _prepare_payload(self, data):
        if data.get("image_prompt") is not None:
            data["image_prompt"] = self._convert_image_to_base64(
                data["image_prompt"]
            )


class FluxProFinetune(FluxBase):
    API_ENDPOINT = "v1/flux-pro-finetuned"
    CATEGORY = "Flux Finetuned"
    INPUT_SPEC = {
        "required": {
            "prompt": ("STRING", {"multiline": True}),
            "finetune_id": (
                "STRING",
                {"multiline": False},
            ),
        },
        "optional": {
            "finetune_strength": (
                "FLOAT",
                {
                    "default": 1.1,
                    "min": 0.0,
                    "max": 2.0,
                },
            ),
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "guidance": (
                "FLOAT",
                {
                    "default": 2.5,
                    "min": 1.5,
                    "max": 5.0,
                },
            ),
            "steps": (
                "INT",
                {"default": 40, "min": 1, "max": 50},
            ),
            "prompt_upsampling": (
                "BOOLEAN",
                {"default": False},
            ),
            "width": (
                "INT",
                {
                    "default": 1024,
                    "min": 256,
                    "max": 1440,
                    "step": 32,
                },
            ),
            "height": (
                "INT",
                {
                    "default": 768,
                    "min": 256,
                    "max": 1440,
                    "step": 32,
                },
            ),
            "safety_tolerance": (
                "INT",
                {"default": 2, "min": 0, "max": 6},
            ),
            "output_format": (
                "STRING",
                {"default": "jpeg"},
            ),
            "image_prompt": ("IMAGE",),
            "image_prompt_strength": (
                "FLOAT",
                {
                    "default": 0.1,
                    "min": 0.0,
                    "max": 1.0,
                },
            ),
        },
    }

    def _prepare_payload(self, data):
        if data.get("image_prompt") is not None:
            data["image_prompt"] = self._convert_image_to_base64(
                data["image_prompt"]
            )


class FluxProCannyFinetune(FluxBase):
    API_ENDPOINT = "v1/flux-pro-1.0-canny-finetuned"
    CATEGORY = "Flux Finetuned"
    INPUT_SPEC = {
        "required": {
            "prompt": ("STRING", {"multiline": True}),
            "control_image": ("IMAGE",),
            "finetune_id": (
                "STRING",
                {"multiline": False},
            ),
        },
        "optional": {
            "finetune_strength": (
                "FLOAT",
                {
                    "default": 1.1,
                    "min": 0.0,
                    "max": 2.0,
                },
            ),
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "guidance": (
                "FLOAT",
                {
                    "default": 30.0,
                    "min": 1.0,
                    "max": 100,
                    "step": 0.1,
                },
            ),
            "steps": (
                "INT",
                {"default": 50, "min": 15, "max": 50},
            ),
            "prompt_upsampling": (
                "BOOLEAN",
                {"default": False},
            ),
            "safety_tolerance": (
                "INT",
                {"default": 2, "min": 0, "max": 6},
            ),
            "output_format": (
                "STRING",
                {"default": "jpeg"},
            ),
        },
    }

    def _prepare_payload(self, data):
        if data.get("control_image") is not None:
            data["control_image"] = self._convert_image_to_base64(
                data["control_image"]
            )


class FluxProDepthFinetune(FluxBase):
    API_ENDPOINT = "v1/flux-pro-1.0-depth-finetuned"
    CATEGORY = "Flux Finetuned"
    INPUT_SPEC = {
        "required": {
            "prompt": ("STRING", {"multiline": True}),
            "control_image": ("IMAGE",),
            "finetune_id": (
                "STRING",
                {"multiline": False},
            ),
        },
        "optional": {
            "finetune_strength": (
                "FLOAT",
                {
                    "default": 1.1,
                    "min": 0.0,
                    "max": 2.0,
                },
            ),
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "guidance": (
                "FLOAT",
                {
                    "default": 15.0,
                    "min": 1.0,
                    "max": 100,
                    "step": 0.1,
                },
            ),
            "steps": (
                "INT",
                {"default": 50, "min": 15, "max": 50},
            ),
            "prompt_upsampling": (
                "BOOLEAN",
                {"default": False},
            ),
            "safety_tolerance": (
                "INT",
                {"default": 2, "min": 0, "max": 6},
            ),
            "output_format": (
                "STRING",
                {"default": "jpeg"},
            ),
        },
    }

    def _prepare_payload(self, data):
        if data.get("control_image") is not None:
            data["control_image"] = self._convert_image_to_base64(
                data["control_image"]
            )


class FluxProFillFinetune(FluxBase):
    API_ENDPOINT = "v1/flux-pro-1.0-fill-finetuned"
    CATEGORY = "Flux Finetuned"
    INPUT_SPEC = {
        "required": {
            "image": ("IMAGE",),
            "finetune_id": (
                "STRING",
                {"multiline": False},
            ),
            "prompt": (
                "STRING",
                {"multiline": True},
            ),
        },
        "optional": {
            "mask": ("MASK",),
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "guidance": (
                "FLOAT",
                {
                    "default": 60.0,
                    "min": 1.5,
                    "max": 100,
                    "step": 0.1,
                },
            ),
            "steps": (
                "INT",
                {"default": 50, "min": 15, "max": 50},
            ),
            "prompt_upsampling": (
                "BOOLEAN",
                {"default": False},
            ),
            "safety_tolerance": (
                "INT",
                {"default": 2, "min": 0, "max": 6},
            ),
            "api_key_override": (
                "STRING",
                {"multiline": False},
            ),
        },
    }

    def _prepare_payload(self, data):
        if data.get("image") is not None:
            data["image"] = self._convert_image_to_base64(
                data["image"]
            )

        if data.get("mask") is not None:
            data["mask"] = self._convert_mask_to_base64(
                data["mask"]
            )


class FluxUltra11Finetune(FluxBase):
    API_ENDPOINT = "v1/flux-pro-1.1-ultra-finetuned"
    CATEGORY = "Flux Finetuned"
    INPUT_SPEC = {
        "required": {
            "prompt": (
                "STRING",
                {"multiline": True},
            ),
            "finetune_id": (
                "STRING",
                {"multiline": False},
            ),
        },
        "optional": {
            "finetune_strength": (
                "FLOAT",
                {
                    "default": 1.2,
                    "min": 0.0,
                    "max": 2.0,
                },
            ),
            "image_prompt": ("IMAGE",),
            "aspect_ratio": (
                "STRING",
                {"default": "1:1"},
            ),
            "raw": (
                "BOOLEAN",
                {
                    "default": False,
                    "label_on": "True",
                    "label_off": "False",
                },
            ),
            "safety_tolerance": (
                "INT",
                {
                    "default": 5,
                    "min": 1,
                    "max": 5,
                    "step": 1,
                },
            ),
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "image_prompt_strength": (
                "FLOAT",
                {
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                },
            ),
            "output_format": (
                "STRING",
                {"default": "png"},
            ),
            "api_key_override": (
                "STRING",
                {"multiline": False},
            ),
        },
    }

    def _prepare_payload(self, data):
        if data.get("image_prompt") is not None:
            data["image_prompt"] = self._convert_image_to_base64(
                data["image_prompt"]
            )


# ---------------------------------------------------------------------------
# FLUX.2 nodes
# ---------------------------------------------------------------------------


def _flux2_reference_inputs():
    return {
        "input_image": ("IMAGE",),
        "input_image_2": ("IMAGE",),
        "input_image_3": ("IMAGE",),
        "input_image_4": ("IMAGE",),
        "input_image_5": ("IMAGE",),
        "input_image_6": ("IMAGE",),
        "input_image_7": ("IMAGE",),
        "input_image_8": ("IMAGE",),
    }


class Flux2Base(FluxBase):
    CATEGORY = "Flux/FLUX.2"
    POLL_ENDPOINT = ""

    def _prepare_payload(self, data):
        for field_name in (
            "input_image",
            "input_image_2",
            "input_image_3",
            "input_image_4",
            "input_image_5",
            "input_image_6",
            "input_image_7",
            "input_image_8",
        ):
            if data.get(field_name) is not None:
                data[field_name] = self._convert_image_to_base64(
                    data[field_name]
                )

        # Width/height = 0 means "let BFL determine it".
        # Do not send zero because API validation may reject it.
        if data.get("width") == 0:
            data.pop("width", None)

        if data.get("height") == 0:
            data.pop("height", None)


def _flux2_pro_input_spec():
    optional = {}
    optional.update(_flux2_reference_inputs())
    optional.update(
        {
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "width": (
                "INT",
                {
                    "default": 0,
                    "min": 0,
                    "max": 4096,
                    "step": 16,
                },
            ),
            "height": (
                "INT",
                {
                    "default": 0,
                    "min": 0,
                    "max": 4096,
                    "step": 16,
                },
            ),
            "prompt_upsampling": (
                "BOOLEAN",
                {
                    "default": True,
                    "label_on": "Enabled",
                    "label_off": "Disabled",
                },
            ),
            "safety_tolerance": (
                "INT",
                {
                    "default": 2,
                    "min": 0,
                    "max": 5,
                    "step": 1,
                },
            ),
            "output_format": (
                ["jpeg", "png", "webp"],
                {"default": "jpeg"},
            ),
            "api_key_override": (
                "STRING",
                {"multiline": False},
            ),
        }
    )

    return {
        "required": {
            "prompt": (
                "STRING",
                {"multiline": True},
            ),
        },
        "optional": optional,
    }


class Flux2ProBase(Flux2Base):
    INPUT_SPEC = _flux2_pro_input_spec()

    def _prepare_payload(self, data):
        super()._prepare_payload(data)

        # FLUX.2 Pro / Max API exposes "disable_pup".
        # Keep ComfyUI's UI positive: prompt_upsampling=True.
        if "prompt_upsampling" in data:
            data["disable_pup"] = not bool(
                data.pop("prompt_upsampling")
            )


class Flux2Pro(Flux2ProBase):
    API_ENDPOINT = "v1/flux-2-pro"


class Flux2ProPreview(Flux2ProBase):
    API_ENDPOINT = "v1/flux-2-pro-preview"


class Flux2Max(Flux2ProBase):
    API_ENDPOINT = "v1/flux-2-max"


class Flux2Flex(Flux2Base):
    API_ENDPOINT = "v1/flux-2-flex"

    _optional = {}
    _optional.update(_flux2_reference_inputs())
    _optional.update(
        {
            "seed": (
                "INT",
                {"default": 0, "min": 0, "max": 4294967294},
            ),
            "width": (
                "INT",
                {
                    "default": 0,
                    "min": 0,
                    "max": 4096,
                    "step": 16,
                },
            ),
            "height": (
                "INT",
                {
                    "default": 0,
                    "min": 0,
                    "max": 4096,
                    "step": 16,
                },
            ),
            "guidance": (
                "FLOAT",
                {
                    "default": 5.0,
                    "min": 1.5,
                    "max": 10.0,
                    "step": 0.1,
                },
            ),
            "steps": (
                "INT",
                {
                    "default": 50,
                    "min": 1,
                    "max": 50,
                },
            ),
            "prompt_upsampling": (
                "BOOLEAN",
                {
                    "default": True,
                    "label_on": "Enabled",
                    "label_off": "Disabled",
                },
            ),
            "safety_tolerance": (
                "INT",
                {
                    "default": 2,
                    "min": 0,
                    "max": 5,
                    "step": 1,
                },
            ),
            "output_format": (
                ["jpeg", "png", "webp"],
                {"default": "jpeg"},
            ),
            "api_key_override": (
                "STRING",
                {"multiline": False},
            ),
        }
    )

    INPUT_SPEC = {
        "required": {
            "prompt": (
                "STRING",
                {"multiline": True},
            ),
        },
        "optional": _optional,
    }
