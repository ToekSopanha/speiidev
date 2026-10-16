"""
Entrypoint for `python -m autodev`.
"""

from __future__ import annotations

import sys
from autodev.cli import main

if __name__ == "__main__":
    sys.exit(main())
