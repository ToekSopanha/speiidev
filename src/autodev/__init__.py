"""
autodev: Interactive Multi-Agent TUI with pluggable agents, model switcher,
diff gate, and conversation memory.
"""

from typing import TYPE_CHECKING
from autodev._version import __version__
from autodev.font import (
    BLOCK_FONT,
    CLAUDE_3D_FONT,
    render_block_text,
    render_claude_3d_text,
)
from autodev.pixel_art import (
    detect_background_mask,
    load_and_resize_image,
    render_pixel_art,
)

if TYPE_CHECKING:
    from autodev.cli import (
        AgentProfile,
        AgentState,
        FileChange,
        PROFILES,
        main,
    )


def __getattr__(name: str):
    if name in ("AgentProfile", "AgentState", "FileChange", "PROFILES", "main"):
        import autodev.cli as cli
        return getattr(cli, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "AgentProfile",
    "AgentState",
    "FileChange",
    "PROFILES",
    "BLOCK_FONT",
    "CLAUDE_3D_FONT",
    "render_block_text",
    "render_claude_3d_text",
    "render_pixel_art",
    "detect_background_mask",
    "load_and_resize_image",
    "main",
    "__version__",
]
