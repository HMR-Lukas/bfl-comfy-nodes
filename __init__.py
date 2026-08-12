from .bfl_flux1 import (
    FluxPro,
    FluxDev,
    FluxPro11,
    FluxCanny,
    FluxDepth,
    FluxUltra11,
    FluxProFill,
    FluxProFinetune,
    FluxProCannyFinetune,
    FluxProDepthFinetune,
    FluxProFillFinetune,
    FluxUltra11Finetune,
)

from .bfl_flux2 import (
    Flux2Pro,
    Flux2ProPreview,
    Flux2Max,
    Flux2Flex,
)

from .bfl_flux3 import (
    Flux3TextToVideo,
    Flux3ImageToVideo,
    Flux3VideoContinuation,
    Flux3DraftEnhance,
    Flux3VideoLegacy,
)

from .bfl_credits import BFLCredits


NODE_CLASS_MAPPINGS = {
    # FLUX 1
    "FLUX 1.0 [pro]": FluxPro,
    "FLUX 1.0 [dev]": FluxDev,
    "FLUX 1.1 [pro]": FluxPro11,
    "FLUX 1.1 [ultra]": FluxUltra11,
    "FLUX 1.0 [depth]": FluxDepth,
    "FLUX 1.0 [canny]": FluxCanny,
    "FLUX 1.0 [fill]": FluxProFill,
    "FLUX 1.0 [pro] Finetuned": FluxProFinetune,
    "FLUX 1.0 [canny] Finetuned": FluxProCannyFinetune,
    "FLUX 1.0 [depth] Finetuned": FluxProDepthFinetune,
    "FLUX 1.0 [fill] Finetuned": FluxProFillFinetune,
    "FLUX 1.1 [ultra] Finetuned": FluxUltra11Finetune,

    # FLUX 2
    "FLUX.2 [pro]": Flux2Pro,
    "FLUX.2 [pro] Preview": Flux2ProPreview,
    "FLUX.2 [max]": Flux2Max,
    "FLUX.2 [flex]": Flux2Flex,

    # FLUX 3
    # Preserve the node type IDs already used by this fork's saved workflows.
    # NODE_DISPLAY_NAME_MAPPINGS removes the provider suffix from what users see.
    "FLUX 3 Text to Video [BFL API]": Flux3TextToVideo,
    "FLUX 3 Image to Video [BFL API]": Flux3ImageToVideo,
    "FLUX 3 Video Continuation [BFL API]": Flux3VideoContinuation,
    "FLUX 3 Draft Enhance [BFL API]": Flux3DraftEnhance,
    "FLUX 3 Video": Flux3VideoLegacy,

    # Account
    "BFL Credits": BFLCredits,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "FLUX 3 Text to Video [BFL API]": "FLUX 3 Text to Video",
    "FLUX 3 Image to Video [BFL API]": "FLUX 3 Image to Video",
    "FLUX 3 Video Continuation [BFL API]": "FLUX 3 Video Continuation",
    "FLUX 3 Draft Enhance [BFL API]": "FLUX 3 Draft Enhance",
    "FLUX 3 Video": "FLUX 3 Video (Legacy)",
}


WEB_DIRECTORY = "./js"
