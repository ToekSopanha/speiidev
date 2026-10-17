import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

import sys
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

if HAS_PIL:
    from autodev.pixel_art import (
        detect_background_mask,
        load_and_resize_image,
        render_pixel_art,
    )


class TestPixelArtRenderer(unittest.TestCase):
    def setUp(self):
        if not HAS_PIL:
            self.skipTest("Pillow not installed")

    def test_white_background_detection(self):
        """BFS mask must identify white borders as background."""
        # Create a small 10x10 white image with red center
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            im = Image.new("RGBA", (10, 10), (255, 255, 255, 255))
            # Draw red 2x2 box in center
            for y in range(4, 6):
                for x in range(4, 6):
                    im.putpixel((x, y), (255, 0, 0, 255))
            im.save(tmp.name)

            grid = load_and_resize_image(tmp.name, width=6, crop_border=False)
            bg_mask = detect_background_mask(grid)
            # Corner (0,0) must be detected as background
            self.assertIn((0, 0), bg_mask)

    def test_dark_background_detection(self):
        """BFS mask must identify dark borders as background when image is dark."""
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            im = Image.new("RGBA", (10, 10), (20, 20, 19, 255))
            for y in range(4, 6):
                for x in range(4, 6):
                    im.putpixel((x, y), (217, 119, 87, 255))
            im.save(tmp.name)

            grid = load_and_resize_image(tmp.name, width=6, crop_border=False)
            bg_mask = detect_background_mask(grid)
            self.assertIn((0, 0), bg_mask)

    def test_render_pixel_art_output(self):
        """render_pixel_art must produce ANSI sequences containing reset code."""
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            im = Image.new("RGBA", (8, 8), (20, 20, 19, 255))
            for x in range(2, 6):
                im.putpixel((x, 3), (217, 119, 87, 255))
                im.putpixel((x, 4), (217, 119, 87, 255))
            im.save(tmp.name)

            out = render_pixel_art(tmp.name, width=8)
            self.assertIn("\033[0m", out)
            self.assertTrue("▄" in out or "▀" in out)


if __name__ == "__main__":
    unittest.main()
