"""Single source of truth for the SpeiiDev version.

Everything else reads from here:
  - ``autodev.__version__`` and ``autodev.cli.APP_VERSION`` import it.
  - ``pyproject.toml`` reads it dynamically (``attr = "autodev._version.__version__"``).
  - ``package.json`` (npm wrapper) is kept in sync by ``scripts/bump_version.py``.

To release a new version, change it in ONE place:

    python scripts/bump_version.py 1.2.3

"""

__version__ = "1.2.0"
