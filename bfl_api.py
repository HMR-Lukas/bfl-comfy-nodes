"""
Backward-compatibility import shim.

The implementation is split into:
- bfl_common.py
- bfl_flux1.py
- bfl_flux2.py

New code should import from those modules directly.
"""

from .bfl_common import *  # noqa: F401,F403
from .bfl_flux1 import *   # noqa: F401,F403
from .bfl_flux2 import *   # noqa: F401,F403
