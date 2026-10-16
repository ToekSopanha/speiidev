import sys
import unittest
from pathlib import Path

# Ensure src/ is on sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from autodev.font import (
    BLOCK_FONT,
    CLAUDE_3D_FONT,
    COLOR_PALETTES,
    render_block_text,
    render_claude_3d_text,
)


class TestFontRenderer(unittest.TestCase):
    def test_claude_3d_font_dimensions(self):
        """Every glyph in CLAUDE_3D_FONT must have exactly 6 lines."""
        for char, lines in CLAUDE_3D_FONT.items():
            self.assertEqual(
                len(lines),
                6,
                f"Glyph '{char}' in CLAUDE_3D_FONT should have exactly 6 lines, got {len(lines)}",
            )

    def test_block_font_dimensions(self):
        """Every glyph in BLOCK_FONT must be a tuple of 2 strings."""
        for char, (top, bot) in BLOCK_FONT.items():
            self.assertIsInstance(top, str)
            self.assertIsInstance(bot, str)

    def test_render_claude_3d_text(self):
        """render_claude_3d_text must produce 6 lines containing box-drawing glyphs."""
        out = render_claude_3d_text("CLAUDE", color="none")
        lines = out.split("\n")
        self.assertEqual(len(lines), 6)
        # Check that double-box drawing characters are present
        self.assertTrue(any("║" in l or "═" in l for l in lines))

    def test_render_block_text_styles(self):
        """render_block_text should respect style='claude' (6 lines) vs style='mini' (2 lines)."""
        out_3d = render_block_text("SPEIIDEV", style="claude", color="none")
        self.assertEqual(len(out_3d.split("\n")), 6)

        out_mini = render_block_text("SPEIIDEV", style="mini", color="none")
        self.assertEqual(len(out_mini.split("\n")), 2)

    def test_case_insensitivity(self):
        """Text rendering should be identical regardless of letter casing."""
        lower = render_block_text("speiidev", style="claude", color="none")
        upper = render_block_text("SPEIIDEV", style="claude", color="none")
        self.assertEqual(lower, upper)

    def test_color_palettes(self):
        """ANSI escape codes should be applied when color is selected, and omitted with 'none'."""
        colored = render_claude_3d_text("TEST", color="claude")
        self.assertIn("\033[38;2;217;119;87m", colored)

        raw = render_claude_3d_text("TEST", color="none")
        self.assertNotIn("\033[", raw)

    def test_digits_and_symbols(self):
        """Numbers and punctuation must render cleanly without errors."""
        out = render_block_text("V4.0-OK!", style="claude", color="none")
        self.assertEqual(len(out.split("\n")), 6)


if __name__ == "__main__":
    unittest.main()
