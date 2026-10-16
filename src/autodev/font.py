"""
font.py: Typography & Banner Renderers for SpeiiDev & Claude Code styles.

Supports two styles:
1. Claude 3D Wireframe Shadow ('claude' / '3d'):
   The signature Anthropic Claude Code 3D isometric drop-shadow block font with
   double-line wireframe outlines (═, ║, ╔, ╗, ╚, ╝) and terracotta coral (#d97757).
2. Compact 2-Line Half-Block ('block' / 'mini'):
   The ultra-compact 2-line terminal half-block style (▄▀▀ █▀█...).
"""

from __future__ import annotations

import argparse
import sys

# Palette
COLOR_PALETTES = {
    "claude": "\033[38;2;217;119;87m",      # Anthropic Terracotta / Coral
    "orange": "\033[38;2;217;119;87m",
    "bokchoy": "\033[38;2;166;227;161m",    # Catppuccin Bok Choy Green
    "green": "\033[38;2;166;227;161m",
    "cyan": "\033[38;2;137;220;235m",
    "peach": "\033[38;2;250;179;135m",
    "none": "",
}
RESET = "\033[0m"


# -------------------------------------------------------------------------
# Style 1: Claude 3D Isometric Double-Line Wireframe Drop Shadow (6-line)
# Matches Anthropic Claude Code terminal branding ('1_CtHP_cjkKw3vjlgENyeF3A.png')
# -------------------------------------------------------------------------
CLAUDE_3D_FONT: dict[str, list[str]] = {
    "A": [
        " ▄█████╗ ",
        "██╔═══██╗",
        "█████████║",
        "██╔═══███║",
        "██║   ███║",
        "╚═╝   ╚══╝╝",
    ],
    "B": [
        "██████╗ ",
        "██╔══██╗",
        "██████╔╝║",
        "██╔══██╗║",
        "██████╔╝║",
        "╚═════╝ ╝",
    ],
    "C": [
        " ▄██████╗",
        " ██╔════╝║",
        " ██║     ║",
        " ██║     ║",
        " ▀██████╗║",
        "  ╚═════╝╝",
    ],
    "D": [
        "██████╗ ",
        "██╔══██╗",
        "██║  ██║",
        "██║  ██║",
        "██████╔╝",
        "╚═════╝╝",
    ],
    "E": [
        "███████╗",
        "██╔════╝║",
        "█████╗  ║",
        "██╔══╝  ║",
        "███████╗║",
        "╚══════╝╝",
    ],
    "F": [
        "███████╗",
        "██╔════╝║",
        "█████╗  ║",
        "██╔══╝  ║",
        "██║     ║",
        "╚═╝     ╝",
    ],
    "G": [
        " ▄██████╗",
        " ██╔════╝║",
        " ██║ ▄███║",
        " ██║ ╚═██║",
        " ▀██████╔╝",
        "  ╚═════╝╝",
    ],
    "H": [
        "██╗   ██╗",
        "██║   ██║",
        "████████║",
        "██╔═══██║",
        "██║   ██║",
        "╚═╝   ╚═╝╝",
    ],
    "I": [
        "  ██╗ ",
        "  ██║ ",
        "  ██║ ",
        "  ██║ ",
        "  ██║ ",
        "  ╚═╝╝",
    ],
    "J": [
        "    ████╗",
        "    ╚═██║",
        "      ██║",
        "      ██║",
        " ▄█████╔╝",
        " ╚═════╝╝",
    ],
    "K": [
        "██╗  ██╗",
        "██║ ██╔╝",
        "█████╔╝║",
        "██╔═██╗║",
        "██║  ██║",
        "╚═╝  ╚═╝╝",
    ],
    "L": [
        "██╗     ",
        "██║     ",
        "██║     ",
        "██║     ",
        "███████╗",
        "╚══════╝╝",
    ],
    "M": [
        "███╗   ███╗",
        "████╗ ████║",
        "██╔████╔██║",
        "██║╚██╔╝██║",
        "██║ ╚═╝ ██║",
        "╚═╝     ╚═╝╝",
    ],
    "N": [
        "███╗   ██╗",
        "████╗  ██║",
        "██╔██╗ ██║",
        "██║╚██╗██║",
        "██║ ╚████║",
        "╚═╝  ╚═══╝╝",
    ],
    "O": [
        " ▄█████╗ ",
        "██╔═══██╗",
        "██║   ██║",
        "██║   ██║",
        "╚██████╔╝",
        " ╚═════╝╝",
    ],
    "P": [
        "██████╗ ",
        "██╔══██╗",
        "██████╔╝║",
        "██╔═══╝ ║",
        "██║     ║",
        "╚═╝     ╝",
    ],
    "Q": [
        " ▄█████╗ ",
        "██╔═══██╗",
        "██║   ██║",
        "██║ ▄▄██║",
        "╚██████╔╝║",
        " ╚═══▀██╗║",
    ],
    "R": [
        "██████╗ ",
        "██╔══██╗",
        "██████╔╝║",
        "██╔══██╗║",
        "██║  ██║",
        "╚═╝  ╚═╝╝",
    ],
    "S": [
        " ▄██████╗",
        " ██╔════╝║",
        " ▀█████╗ ║",
        "  ╚═══██╗║",
        " ██████╔╝║",
        " ╚═════╝ ╝",
    ],
    "T": [
        "▀███████╗",
        " ╚═██╔══╝",
        "   ██║   ",
        "   ██║   ",
        "   ██║   ",
        "   ╚═╝╝  ",
    ],
    "U": [
        "██╗   ██╗",
        "██║   ██║",
        "██║   ██║",
        "██║   ██║",
        "╚███████║",
        " ╚══════╝╝",
    ],
    "V": [
        "██╗   ██╗",
        "██║   ██║",
        "██║   ██║",
        "╚██╗ ██╔╝",
        " ╚████╔╝║",
        "  ╚═══╝ ╝",
    ],
    "W": [
        "██╗    ██╗",
        "██║    ██║",
        "██║ █╗ ██║",
        "██║███╗██║",
        "╚███╔███╔╝",
        " ╚══╝╚══╝╝",
    ],
    "X": [
        "██╗   ██╗",
        "╚██╗ ██╔╝",
        " ╚████╔╝ ",
        " ██╔═██╗ ",
        "██╔╝ ╚██╗",
        "╚═╝   ╚═╝╝",
    ],
    "Y": [
        " ██╗   ██╗",
        " ╚██╗ ██╔╝",
        "  ╚████╔╝ ",
        "   ╚██╔╝  ",
        "    ██║   ",
        "    ╚═╝╝  ",
    ],
    "Z": [
        "███████╗",
        "╚════██║",
        "  ▄███╔╝",
        " ███╔══╝",
        "███████╗",
        "╚══════╝╝",
    ],
    " ": [
        "    ",
        "    ",
        "    ",
        "    ",
        "    ",
        "    ",
    ],
    "0": [
        " ▄█████╗ ",
        "██╔═████╗",
        "██║██╔██║",
        "████╔╝██║",
        "╚██████╔╝",
        " ╚═════╝╝",
    ],
    "1": [
        " ▄██╗ ",
        "▄███║ ",
        "  ██║ ",
        "  ██║ ",
        " ████╗",
        " ╚═══╝╝",
    ],
    "2": [
        " ▄█████╗",
        "▀▀═══██║",
        " ▄█████║",
        "██╔════╝",
        "███████╗",
        "╚══════╝╝",
    ],
    "3": [
        " ▄█████╗",
        " ▀▀══██║",
        "  ▄████║",
        "  ╚══██║",
        " ██████║",
        " ╚═════╝╝",
    ],
    "4": [
        " ██╗  ██╗",
        " ██║  ██║",
        " ███████║",
        " ╚════██║",
        "      ██║",
        "      ╚═╝╝",
    ],
    "5": [
        "███████╗",
        "██╔════╝",
        "███████╗",
        "╚════██║",
        "███████║",
        "╚══════╝╝",
    ],
    "6": [
        " ▄█████╗ ",
        " ██╔═══╝ ",
        " ███████╗",
        " ██╔═══██╗",
        " ╚██████╔╝",
        "  ╚═════╝╝",
    ],
    "7": [
        "▀███████╗",
        " ╚════██║",
        "    ▄██╔╝",
        "   ███╔╝ ",
        "   ██║   ",
        "   ╚═╝╝  ",
    ],
    "8": [
        " ▄█████╗ ",
        "██╔═══██╗",
        "╚██████╔╝",
        "██╔═══██╗",
        "╚██████╔╝",
        " ╚═════╝╝",
    ],
    "9": [
        " ▄█████╗ ",
        "██╔═══██╗",
        "╚███████║",
        " ╚════██║",
        " ██████╔╝",
        " ╚═════╝╝",
    ],
    "-": [
        "        ",
        "        ",
        " ██████╗",
        " ╚═════╝╝",
        "        ",
        "        ",
    ],
    ".": [
        "     ",
        "     ",
        "     ",
        "     ",
        " ▄██╗",
        " ╚══╝╝",
    ],
    "!": [
        " ██╗",
        " ██║",
        " ██║",
        " ╚═╝",
        " ▄█╗",
        " ╚═╝╝",
    ],
    "?": [
        " ▄█████╗",
        " ▀▀══██║",
        "   ▄██╔╝",
        "   ╚═╝  ",
        "   ▄█╗  ",
        "   ╚═╝╝ ",
    ],
}


# -------------------------------------------------------------------------
# Style 2: Compact 2-Line Half-Block Font
# -------------------------------------------------------------------------
BLOCK_FONT: dict[str, tuple[str, str]] = {
    "A": ("▄▀█", "█▀█"),
    "B": ("█▀▄", "█▄▀"),
    "C": ("▄▀▀", "▀▄▄"),
    "D": ("█▀▄", "█▄▀"),
    "E": ("█▀▀", "██▄"),
    "F": ("█▀▀", "█░░"),
    "G": ("▄▀▀", "█▄█"),
    "H": ("█░█", "█▀█"),
    "I": ("█", "█"),
    "J": ("░░█", "▀▄█"),
    "K": ("█▄▀", "█░█"),
    "L": ("█░░", "█▄▄"),
    "M": ("█▀▀█", "█░░█"),
    "N": ("█▀▄", "█░█"),
    "O": ("█▀█", "█▄█"),
    "P": ("█▀█", "█▀▀"),
    "Q": ("█▀█", "▀▀█"),
    "R": ("█▀█", "█▀▄"),
    "S": ("▄▀▀", "▄██"),
    "T": ("▀█▀", "░█░"),
    "U": ("█░█", "█▄█"),
    "V": ("█░█", "▀▄▀"),
    "W": ("█░░█", "▀▄▄▀"),
    "X": ("▀▄▀", "█░█"),
    "Y": ("█░█", "░█░"),
    "Z": ("▀▀█", "█▄▄"),
    " ": ("  ", "  "),
    "0": ("█▀█", "█▄█"),
    "1": ("▄█░", "░█░"),
    "2": ("▀▀█", "█▄▄"),
    "3": ("▀▀█", "▄▄█"),
    "4": ("█░█", "▀▀█"),
    "5": ("█▀▀", "▄▄█"),
    "6": ("█▀▀", "█▄█"),
    "7": ("▀▀█", "░░█"),
    "8": ("█▀█", "█▄█"),
    "9": ("█▀█", "▀▀█"),
    "-": ("▄▄", "░░"),
    "_": ("░░", "▄▄"),
    ".": ("░", "▄"),
    ":": ("•", "•"),
    "!": ("█", "•"),
    "?": ("▀▀█", "░•░"),
    "/": ("▄▀", "▀▄"),
    "+": ("▄█▄", "░█░"),
}


def render_claude_3d_text(
    text: str,
    color: str = "claude",
    letter_spacing: str = " ",
) -> str:
    """
    Render text using Anthropic Claude Code's 3D isometric double-line
    wireframe drop-shadow block art font.
    """
    lines: list[str] = ["", "", "", "", "", ""]
    color_code = COLOR_PALETTES.get(color.lower(), "")
    use_color = bool(color_code)

    for char in text.upper():
        pat = CLAUDE_3D_FONT.get(char, CLAUDE_3D_FONT[" "])
        for r in range(6):
            lines[r] += pat[r] + letter_spacing

    if use_color:
        return "\n".join(f"{color_code}{line.rstrip()}{RESET}" for line in lines)
    return "\n".join(line.rstrip() for line in lines)


def render_block_text(
    text: str,
    style: str = "claude",
    color: str = "claude",
    letter_spacing: str = " ",
) -> str:
    """
    Render a text string as terminal block art font.

    Args:
        text: Input string.
        style: 'claude' (or '3d' for 6-line isometric wireframe shadow)
               or 'mini' (or '2line' for compact 2-line half-block).
        color: 'claude' (terracotta orange), 'bokchoy' (green), 'none', etc.
        letter_spacing: Separator string between characters.
    """
    s = style.lower().strip()
    if s in ("claude", "3d", "shadow", "isometric"):
        return render_claude_3d_text(text, color=color, letter_spacing=letter_spacing)

    # Mini 2-line style
    top_row: list[str] = []
    bot_row: list[str] = []

    for char in text.upper():
        top, bot = BLOCK_FONT.get(char, (char, char))
        top_row.append(top)
        bot_row.append(bot)

    res = f"{letter_spacing.join(top_row)}\n{letter_spacing.join(bot_row)}"
    color_code = COLOR_PALETTES.get(color.lower(), "")
    if color_code:
        return f"{color_code}{res}{RESET}"
    return res


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render text in Claude Code 3D wireframe shadow or compact 2-line font."
    )
    parser.add_argument("text", nargs="*", default=["CLAUDE CODE"], help="Text to render")
    parser.add_argument(
        "--style",
        choices=["claude", "3d", "mini", "2line"],
        default="claude",
        help="Font style: 'claude' (3D shadow) or 'mini' (2-line)",
    )
    parser.add_argument(
        "--color",
        choices=list(COLOR_PALETTES),
        default="claude",
        help="Color theme: 'claude' (#d97757 coral), 'bokchoy' (#a6e3a1 green), 'none'",
    )
    parser.add_argument("--raw", action="store_true", help="Omit ANSI color codes (for markdown)")
    args = parser.parse_args()

    input_text = " ".join(args.text)
    color = "none" if args.raw else args.color
    print(render_block_text(input_text, style=args.style, color=color))
    return 0


if __name__ == "__main__":
    sys.exit(main())
