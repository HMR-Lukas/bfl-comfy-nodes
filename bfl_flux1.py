from .bfl_common import FluxBase


class Flux1Base(FluxBase):
    CATEGORY = "Flux/FLUX 1"


class FluxPro(Flux1Base):
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


class FluxDev(Flux1Base):
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


class FluxPro11(Flux1Base):
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


class FluxProFill(Flux1Base):
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


class FluxCanny(Flux1Base):
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


class FluxDepth(Flux1Base):
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


class FluxUltra11(Flux1Base):
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


class FluxProFinetune(Flux1Base):
    API_ENDPOINT = "v1/flux-pro-finetuned"
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


class FluxProCannyFinetune(Flux1Base):
    API_ENDPOINT = "v1/flux-pro-1.0-canny-finetuned"
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


class FluxProDepthFinetune(Flux1Base):
    API_ENDPOINT = "v1/flux-pro-1.0-depth-finetuned"
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


class FluxProFillFinetune(Flux1Base):
    API_ENDPOINT = "v1/flux-pro-1.0-fill-finetuned"
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


class FluxUltra11Finetune(Flux1Base):
    API_ENDPOINT = "v1/flux-pro-1.1-ultra-finetuned"
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
