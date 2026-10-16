#!/usr/bin/env python3
"""
render_pixel_art.py: Terminal Pixel Art Renderer using TrueColor ANSI sequences.

Loads an image (PNG, JPEG, WebP, etc.) using Pillow or OpenCV, downsamples it
to fit standard terminal widths (default 32-48 cols), and renders it using
terminal half-block characters (\\u2584 / '▄' and \\u2580 / '▀') with TrueColor
escape sequences (\\033[38;2;R;G;Bm and \\033[48;2;R;G;Bm), while cleanly handling
white/transparent backgrounds.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import deque
from pathlib import Path
from typing import Tuple

# Backend detection (Pillow or OpenCV)
HAS_PIL = False
HAS_CV2 = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    pass

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    pass

RESET = "\033[0m"


def load_and_resize_image(
    image_path: str | Path,
    width: int = 40,
    crop_border: bool = False,
    threshold: int = 242,
    resample_method: str = "lanczos",
) -> list[list[Tuple[int, int, int, int]]]:
    """
    Load an image using Pillow (or OpenCV) and return a 2D grid of RGBA pixels.
    Height is adjusted to preserve aspect ratio and rounded to an even number.
    """
    path_str = str(Path(image_path).expanduser().resolve())
    if not os.path.exists(path_str):
        raise FileNotFoundError(f"Image not found at path: {path_str}")

    if HAS_PIL:
        im = Image.open(path_str).convert("RGBA")

        if crop_border:
            # Find bounding box of non-background content
            px_raw = im.load()
            w_orig, h_orig = im.size
            # Auto-detect if image background is dark or light from corners
            corners_raw = [px_raw[0, 0], px_raw[w_orig - 1, 0], px_raw[0, h_orig - 1], px_raw[w_orig - 1, h_orig - 1]]
            bg_is_dark_raw = sum(1 for p in corners_raw if p[3] < 32 or (p[0] < 40 and p[1] < 40 and p[2] < 40)) >= 2
            min_x, min_y, max_x, max_y = w_orig, h_orig, 0, 0
            has_content = False

            for y in range(h_orig):
                for x in range(w_orig):
                    r, g, b, a = px_raw[x, y]
                    is_bg_pixel = (
                        a < 32
                        or (bg_is_dark_raw and (r < 40 and g < 40 and b < 40))
                        or (not bg_is_dark_raw and (r > threshold and g > threshold and b > threshold))
                    )
                    if not is_bg_pixel:
                        if x < min_x: min_x = x
                        if x > max_x: max_x = x
                        if y < min_y: min_y = y
                        if y > max_y: max_y = y
                        has_content = True
            if has_content and (max_x > min_x) and (max_y > min_y):
                im = im.crop((min_x, min_y, max_x + 1, max_y + 1))

        orig_w, orig_h = im.size
        aspect = orig_h / orig_w
        height = max(2, int(round(width * aspect)))
        if height % 2 != 0:
            height += 1

        resample_filter = {
            "nearest": Image.Resampling.NEAREST,
            "box": Image.Resampling.BOX,
            "bilinear": Image.Resampling.BILINEAR,
            "lanczos": Image.Resampling.LANCZOS,
        }.get(resample_method.lower(), Image.Resampling.LANCZOS)

        im_resized = im.resize((width, height), resample_filter)
        px = im_resized.load()

        grid: list[list[Tuple[int, int, int, int]]] = []
        for y in range(height):
            row = [px[x, y] for x in range(width)]
            grid.append(row)
        return grid

    elif HAS_CV2:
        img_bgr = cv2.imread(path_str, cv2.IMREAD_UNCHANGED)
        if img_bgr is None:
            raise ValueError(f"OpenCV failed to read image at: {path_str}")

        if len(img_bgr.shape) == 2:
            img_rgba = cv2.cvtColor(img_bgr, cv2.COLOR_GRAY2RGBA)
        elif img_bgr.shape[2] == 3:
            img_rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGBA)
        else:
            img_rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGRA2RGBA)

        orig_h, orig_w = img_rgba.shape[:2]
        aspect = orig_h / orig_w
        height = max(2, int(round(width * aspect)))
        if height % 2 != 0:
            height += 1

        interp = cv2.INTER_NEAREST if resample_method.lower() == "nearest" else cv2.INTER_AREA
        resized = cv2.resize(img_rgba, (width, height), interpolation=interp)

        grid = []
        for y in range(height):
            row = [tuple(int(c) for c in resized[y, x]) for x in range(width)]
            grid.append(row)
        return grid

    else:
        raise ImportError(
            "Neither Pillow nor OpenCV is installed. Run 'pip install pillow' to enable image rendering."
        )


def detect_background_mask(
    grid: list[list[Tuple[int, int, int, int]]],
    threshold: int = 242,
) -> set[tuple[int, int]]:
    """
    Flood-fill from image boundaries to identify exterior transparent/white background pixels,
    preserving light or cream-colored details inside the subject.
    """
    h = len(grid)
    w = len(grid[0])
    is_bg: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()

    # Auto-detect if background is dark or light from border pixels
    corners = [grid[0][0], grid[0][w - 1], grid[h - 1][0], grid[h - 1][w - 1]]
    bg_is_dark = sum(1 for (r, g, b, a) in corners if a < 32 or (r < 40 and g < 40 and b < 40)) >= 2

    def is_candidate(x: int, y: int) -> bool:
        r, g, b, a = grid[y][x]
        if a < 32:
            return True
        if bg_is_dark:
            return r < 40 and g < 40 and b < 40
        return r > threshold and g > threshold and b > threshold

    # Seed BFS queue from image borders
    for x in range(w):
        for y in (0, h - 1):
            if (x, y) not in is_bg and is_candidate(x, y):
                is_bg.add((x, y))
                queue.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if (x, y) not in is_bg and is_candidate(x, y):
                is_bg.add((x, y))
                queue.append((x, y))

    # BFS 4-directional flood fill
    while queue:
        cx, cy = queue.popleft()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in is_bg:
                if is_candidate(nx, ny):
                    is_bg.add((nx, ny))
                    queue.append((nx, ny))

    return is_bg


def render_pixel_art(
    image_path: str | Path,
    width: int = 40,
    threshold: int = 242,
    crop_border: bool = False,
    resample_method: str = "lanczos",
) -> str:
    """
    Renders an image as TrueColor terminal pixel art using terminal half-blocks.

    Each text row covers 2 vertical pixels:
    - Top pixel: rendered on the upper half of the text cell.
    - Bottom pixel: rendered on the lower half of the text cell.
    - Uses lower half-block \\u2584 ('▄') and upper half-block \\u2580 ('▀')
      paired with TrueColor escape codes:
        \\033[38;2;R;G;Bm (Foreground color)
        \\033[48;2;R;G;Bm (Background color)
    - Automatically handles transparent and white backgrounds.
    - Resets with \\033[0m at the end of each terminal row.
    """
    grid = load_and_resize_image(
        image_path,
        width=width,
        crop_border=crop_border,
        threshold=threshold,
        resample_method=resample_method,
    )
    bg_mask = detect_background_mask(grid, threshold=threshold)

    height = len(grid)
    out_lines: list[str] = []

    for y in range(0, height, 2):
        line_parts: list[str] = []
        for x in range(width):
            top_is_bg = (x, y) in bg_mask
            bot_is_bg = (x, y + 1) in bg_mask if (y + 1 < height) else True

            top_r, top_g, top_b = grid[y][x][:3]
            bot_r, bot_g, bot_b = grid[y + 1][x][:3] if (y + 1 < height) else (0, 0, 0)

            if top_is_bg and bot_is_bg:
                # Both pixels are transparent/background
                line_parts.append(" ")
            elif top_is_bg and not bot_is_bg:
                # Top is background, bottom is colored:
                # Lower half-block '▄' with bottom color as foreground
                line_parts.append(f"\033[38;2;{bot_r};{bot_g};{bot_b}m▄")
            elif not top_is_bg and bot_is_bg:
                # Top is colored, bottom is background:
                # Upper half-block '▀' with top color as foreground
                line_parts.append(f"\033[38;2;{top_r};{top_g};{top_b}m▀")
            else:
                # Both pixels colored:
                # Background code sets top pixel (upper half),
                # Foreground code sets bottom pixel (lower half of '▄')
                line_parts.append(
                    f"\033[48;2;{top_r};{top_g};{top_b}m\033[38;2;{bot_r};{bot_g};{bot_b}m▄"
                )

        # Reset terminal styling at the end of each row
        line_parts.append(RESET)
        out_lines.append("".join(line_parts))

    return "\n".join(out_lines) + "\n"


def print_pixel_art(
    image_path: str | Path,
    width: int = 40,
    threshold: int = 242,
    crop_border: bool = False,
    resample_method: str = "lanczos",
) -> None:
    """Renders and prints TrueColor pixel art directly to stdout."""
    output = render_pixel_art(
        image_path=image_path,
        width=width,
        threshold=threshold,
        crop_border=crop_border,
        resample_method=resample_method,
    )
    sys.stdout.write(output)
    sys.stdout.flush()


def main() -> int:
    default_path = (
        "/Users/mac/Downloads/pixel-art-green-bok-choy-cabbage-icon-illustration-fresh-healthy-food-design-472467971.webp"
    )
    parser = argparse.ArgumentParser(
        description="Render an image as TrueColor ANSI pixel art in the terminal using half-blocks."
    )
    parser.add_argument(
        "image_path",
        nargs="?",
        default=default_path,
        help=f"Path to the image file (default: {default_path})",
    )
    parser.add_argument(
        "-w",
        "--width",
        type=int,
        default=40,
        help="Target column width (default: 40, typically 32 to 48)",
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=int,
        default=242,
        help="RGB brightness cutoff (0-255) for white background detection (default: 242)",
    )
    parser.add_argument(
        "-c",
        "--crop",
        action="store_true",
        help="Auto-crop outer whitespace padding before scaling",
    )
    parser.add_argument(
        "--resample",
        choices=["lanczos", "nearest", "box", "bilinear"],
        default="lanczos",
        help="Downsampling resampling filter (default: lanczos)",
    )

    args = parser.parse_args()

    try:
        print_pixel_art(
            image_path=args.image_path,
            width=args.width,
            threshold=args.threshold,
            crop_border=args.crop,
            resample_method=args.resample,
        )
        return 0
    except Exception as exc:
        sys.stderr.write(f"\033[31mError:\033[0m {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
