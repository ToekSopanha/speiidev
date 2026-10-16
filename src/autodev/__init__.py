"""
autodev: Interactive Multi-Agent TUI with pluggable agents, model switcher,
diff gate, and conversation memory.
"""

from autodev.cli import (
    AgentProfile,
    AgentState,
    FileChange,
    PROFILES,
    main,
)
from autodev.font import (
    BLOCK_FONT,
    CLAUDE_3D_FONT,
    render_block_text,
    render_claude_3d_text,
)

__version__ = "1.0.0"
__all__ = [
    "AgentProfile",
    "AgentState",
    "FileChange",
    "PROFILES",
    "BLOCK_FONT",
    "CLAUDE_3D_FONT",
    "render_block_text",
    "render_claude_3d_text",
    "main",
    "__version__",
]
