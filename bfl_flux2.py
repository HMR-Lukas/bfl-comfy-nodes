import torch

from .bfl_common import FluxBase


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
    CATEGORY = "Flux/FLUX 2"
    POLL_ENDPOINT = ""

    def _prepare_payload(self, data):
        # Flatten all connected reference IMAGE inputs, including ComfyUI image
        # batches, into BFL's sequential input_image...input_image_8 fields.
        # This mirrors the behaviour users expect from the official nodes and
        # avoids silently dropping every batch frame except the first.
        reference_fields = (
            "input_image",
            "input_image_2",
            "input_image_3",
            "input_image_4",
            "input_image_5",
            "input_image_6",
            "input_image_7",
            "input_image_8",
        )

        references = []

        for field_name in reference_fields:
            value = data.pop(field_name, None)
            if value is None:
                continue

            if isinstance(value, torch.Tensor) and value.ndim == 4:
                references.extend(value[i] for i in range(value.shape[0]))
            else:
                references.append(value)

        if len(references) > 8:
            raise ValueError(
                f"FLUX.2 supports at most 8 API reference images; got {len(references)}."
            )

        for index, image in enumerate(references):
            field_name = "input_image" if index == 0 else f"input_image_{index + 1}"
            data[field_name] = self._convert_image_to_base64(image)

        # Width/height = 0 means "let BFL determine it".
        # Do not send zero because API validation may reject it.
        width = data.get("width")
        height = data.get("height")

        if width == 0:
            data.pop("width", None)
            width = None

        if height == 0:
            data.pop("height", None)
            height = None

        # FLUX.2 supports up to 4MP output. Dimensions are multiples of 16.
        # Keep the generous per-side UI range, but reject invalid combinations
        # before they consume an API request.
        for name, value in (("width", width), ("height", height)):
            if value is None:
                continue
            if value < 64:
                raise ValueError(f"FLUX.2 {name} must be at least 64 pixels or 0 for auto.")
            if value % 16 != 0:
                raise ValueError(f"FLUX.2 {name} must be a multiple of 16.")

        if width is not None and height is not None:
            max_pixels = 4 * 1024 * 1024
            if width * height > max_pixels:
                raise ValueError(
                    f"FLUX.2 output is limited to 4MP; got {width}x{height} "
                    f"({width * height / (1024 * 1024):.2f}MP)."
                )


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
