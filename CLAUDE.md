# SpeiiDev Project Guidelines

## Identity & Branding
- **Name**: SpeiiDev
- **Mascot / Logo**: Pixel Art Green Bok Choy Cabbage (`render_pixel_art.py` TrueColor ANSI terminal renderer)
- **Color Accents**:
  - Catppuccin Bok Choy Green (`#a6e3a1`)
  - Anthropic Terracotta Coral (`#d97757`)

## Typography & ASCII Art Styles

### Style 1: Claude 3D Wireframe Shadow (from image `1_CtHP_cjkKw3vjlgENyeF3A.png`)
Chunky block letters with double-line isometric drop shadow:
```
 ▄██████╗ ██╗       ▄█████╗  ██╗   ██╗ ██████╗  ███████╗
 ██╔════╝║ ██║      ██╔═══██╗ ██║   ██║ ██╔══██╗ ██╔════╝║
 ██║     ║ ██║      █████████║ ██║   ██║ ██║  ██║ █████╗  ║
 ██║     ║ ██║      ██╔═══███║ ██║   ██║ ██║  ██║ ██╔══╝  ║
 ▀██████╗║ ███████╗ ██║   ███║ ╚███████║ ██████╔╝ ███████╗║
  ╚═════╝╝ ╚══════╝╝ ╚═╝   ╚══╝╝  ╚══════╝╝ ╚═════╝╝ ╚══════╝╝
```

### Style 2: Compact 2-Line Half-Block Font
For narrow terminals and compact banners:
```
▄▀▀ █▀█ █▀▀ █ █ █▀▄ █▀▀ █░█
▄██ █▀▀ ██▄ █ █ █▄▀ ██▄ ▀▄▀
```

### Rendering Tools
- **Terminal CLI**:
  - `block-font "MY TEXT"` (3D wireframe shadow)
  - `block-font "MY TEXT" --style mini` (2-line)
  - `speiidev --font "MY TEXT"`
- **Python Module**:
  - `from autodev.font import render_block_text, render_claude_3d_text`
- **SpeiiDev REPL**:
  - `/font <text>` (3D wireframe shadow)
  - `/font --mini <text>` (2-line)

## Claude Code Custom Output Style
A custom output style `speiidev-block` is configured in:
- Project: `.claude/output-styles/speiidev-block.md`
- Global: `~/.claude/output-styles/speiidev-block.md`

To activate in Claude Code:
```
/output-style speiidev-block
```
