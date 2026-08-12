import requests

from .bfl_common import REQUEST_TIMEOUT_SECONDS, FluxBase, get_api_key


class BFLCredits:
    """
    Standalone ComfyUI output node that shows the currently available
    Black Forest Labs credits.

    The node does not need to be connected to another node.
    """

    RETURN_TYPES = ("FLOAT", "STRING")
    RETURN_NAMES = ("credits", "display")
    FUNCTION = "get_credits"
    CATEGORY = "Flux/Account"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
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
    def IS_CHANGED(cls, api_key_override=""):
        # The credit balance is external state, so always refresh it.
        return float("NaN")

    def get_credits(self, api_key_override=""):
        api_key = (api_key_override or "").strip() or get_api_key()

        if not api_key:
            raise Exception(
                "No Black Forest Labs API key set. "
                "Set environment variable BFL_API_KEY, create bfl_api_key.txt "
                "next to bfl_api.py, or use api_key_override."
            )

        headers = {
            "Accept": "application/json",
            "x-key": api_key,
        }

        try:
            response = requests.get(
                "https://api.bfl.ai/v1/credits",
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise Exception(
                f"BFL Credits connection error: {exc}"
            ) from exc

        if not response.ok:
            raise Exception(FluxBase._format_api_error(response))

        try:
            payload = response.json()
        except ValueError as exc:
            raise Exception(
                "BFL Credits API returned invalid JSON."
            ) from exc

        if "credits" not in payload:
            raise Exception(
                f"BFL Credits API response did not contain credits: {payload}"
            )

        credits = float(payload["credits"])
        display = f"BFL Credits available: {credits:.2f}"

        print(f"[BFL] {display}")

        return {
            "ui": {
                "text": [display],
            },
            "result": (
                credits,
                display,
            ),
        }