import base64
import os
import time
from io import BytesIO

import numpy as np
import requests
import torch
from PIL import Image


API_ROOTS = {
    "Global": "https://api.bfl.ai/",
    "EU": "https://api.eu.bfl.ai/",
    "US": "https://api.us.bfl.ai/",
    # Backward-compatible region labels used by older workflows.
    "EU1": "https://api.eu.bfl.ai/",
    "US1": "https://api.us.bfl.ai/",
}

DEFAULT_REGION = "EU"

REQUEST_TIMEOUT_SECONDS = 60
GENERATION_TIMEOUT_SECONDS = 300
POLL_INTERVAL_SECONDS = 0.5


def get_api_key():
    """Load the BFL API key from the environment or bfl_api_key.txt."""
    api_key = os.environ.get("BFL_API_KEY")
    if api_key:
        return api_key.strip()

    directory = os.path.dirname(os.path.realpath(__file__))
    key_file = os.path.join(directory, "bfl_api_key.txt")

    if os.path.exists(key_file):
        with open(key_file, "r", encoding="utf-8") as handle:
            api_key = handle.read().strip()
            if api_key:
                return api_key

    return None


def format_api_error(response):
    try:
        detail = response.json()
    except ValueError:
        detail = response.text

    return f"BFL API Error HTTP {response.status_code}: {detail}"


def format_cost(cost):
    if cost is None:
        return None

    try:
        value = float(cost)
    except (TypeError, ValueError):
        return None

    return f"{value:g} BFL credits"


class FluxBase:
    """
    Shared image endpoint transport for FLUX 1 and FLUX 2.

    Current BFL endpoints return an absolute polling_url. A legacy id-based
    fallback is retained so older endpoints/workflows keep working.
    """

    API_ENDPOINT = ""
    POLL_ENDPOINT = "v1/get_result"
    ACCEPT = "application/json"
    INPUT_SPEC = {}
    CATEGORY = "Flux"

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "call"

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

    def call(self, *args, **kwargs):
        region = kwargs.get("region", DEFAULT_REGION)
        api_key_override = kwargs.get("api_key_override")
        api_key = (api_key_override or "").strip() or get_api_key()

        if not api_key:
            raise Exception(
                "No Black Forest Labs API key set. "
                "Set BFL_API_KEY, create bfl_api_key.txt next to this package, "
                "or use api_key_override."
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
            raise Exception(format_api_error(response))

        content_type = response.headers.get("Content-Type", "")
        if content_type.startswith("image/"):
            image_result = self._process_image_response(response)
            return {"result": image_result}

        try:
            submit = response.json()
        except ValueError as exc:
            raise Exception(
                f"BFL API returned invalid JSON "
                f"(HTTP {response.status_code}): {response.text[:500]}"
            ) from exc

        cost = submit.get("cost")
        image_result = self._handle_submit(
            submit=submit,
            headers=headers,
            region=region,
        )

        return self._node_output(image_result, cost)

    def _node_output(self, result_tuple, cost):
        ui = {}

        try:
            numeric_cost = float(cost) if cost is not None else None
        except (TypeError, ValueError):
            numeric_cost = None

        if numeric_cost is not None:
            text = f"BFL cost: {numeric_cost:g} credits"
            print(f"[BFL] {text}")
            ui["bfl_cost"] = [numeric_cost]
            ui["text"] = [text]

        return {
            "ui": ui,
            "result": result_tuple,
        }

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

    def _handle_submit(self, submit, headers, region=DEFAULT_REGION):
        polling_url = submit.get("polling_url")

        if polling_url:
            return self._poll_for_result(
                polling_url=polling_url,
                headers=headers,
                region=region,
                task_id=submit.get("id"),
            )

        task_id = submit.get("id")
        if task_id and self.POLL_ENDPOINT:
            return self._poll_for_result(
                polling_url=None,
                headers=headers,
                region=region,
                task_id=task_id,
            )

        if submit.get("status") == "Ready":
            return self._ready_result_to_image(submit)

        raise Exception(
            f"BFL API response contained neither polling_url nor task id: {submit}"
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

            if response.status_code == 202:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            if not response.ok:
                raise Exception(format_api_error(response))

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
                "Task not found",
            }:
                raise Exception(f"BFL API generation failed: {result}")

            time.sleep(POLL_INTERVAL_SECONDS)

    def _ready_result_to_image(self, result):
        result_data = result.get("result") or {}

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
            if image.ndim == 4:
                image = image[0]

            image_np = image.detach().cpu().numpy()
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
        # Kept for backward compatibility with bfl_credits.py and third-party code.
        return format_api_error(response)
