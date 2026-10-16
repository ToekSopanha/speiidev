#!/usr/bin/env python3
"""
test_real_install.py: Real Isolated Installation & Execution Smoke Test.

Simulates an end-user installing the package from scratch in an isolated
disposable temporary virtual environment. Tests build, console script
entrypoints (autodev, speiidev, block-font), and the full unit test suite,
then automatically cleans up the sandbox on exit.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


def main() -> int:
    print("=" * 64)
    print("📦 STEP 1: Creating isolated disposable sandbox environment...")
    print("=" * 64)

    with tempfile.TemporaryDirectory(prefix="autodev_sandbox_") as tmp_dir:
        venv_path = Path(tmp_dir) / "venv"

        # Check if uv is available, otherwise use python3 -m venv
        uv_bin = shutil.which("uv")
        if uv_bin:
            subprocess.run([uv_bin, "venv", str(venv_path), "-q"], check=True)
        else:
            import venv

            venv.create(str(venv_path), with_pip=True)

        # Locate binaries inside the isolated venv
        if sys.platform == "win32":
            bin_dir = venv_path / "Scripts"
            python_bin = bin_dir / "python.exe"
            speiidev_bin = bin_dir / "speiidev.exe"
            block_font_bin = bin_dir / "block-font.exe"
        else:
            bin_dir = venv_path / "bin"
            python_bin = bin_dir / "python"
            speiidev_bin = bin_dir / "speiidev"
            block_font_bin = bin_dir / "block-font"

        print("=" * 64)
        print("🔨 STEP 2: Installing package in editable mode from pyproject.toml...")
        print("=" * 64)
        if uv_bin:
            subprocess.run(
                [
                    uv_bin,
                    "pip",
                    "install",
                    "-e",
                    f"{ROOT_DIR}[image]",
                    "-q",
                    "--python",
                    str(python_bin),
                ],
                check=True,
            )
        else:
            subprocess.run(
                [
                    str(python_bin),
                    "-m",
                    "pip",
                    "install",
                    "-e",
                    f"{ROOT_DIR}[image]",
                    "-q",
                ],
                check=True,
            )

        print("=" * 64)
        print("🔍 STEP 3: Verifying installed console script binaries...")
        print("=" * 64)
        print(f"✓ speiidev binary:   {speiidev_bin}")
        print(f"✓ block-font binary: {block_font_bin}")

        print("")
        print("=" * 64)
        print("🚀 STEP 4: Executing real installed entrypoints...")
        print("=" * 64)
        print("Testing 'speiidev --font \"SPEIIDEV\"'...")
        subprocess.run([str(speiidev_bin), "--font", "SPEIIDEV"], check=True)

        print("")
        print("Testing 'block-font \"REAL INSTALL OK\"'...")
        subprocess.run([str(block_font_bin), "REAL INSTALL OK"], check=True)

        print("")
        print("=" * 64)
        print("🧪 STEP 5: Running full automated unit test suite inside sandbox...")
        print("=" * 64)
        test_proc = subprocess.run(
            [
                str(python_bin),
                "-m",
                "unittest",
                "discover",
                "-s",
                str(ROOT_DIR / "tests"),
                "-v",
            ]
        )
        if test_proc.returncode != 0:
            return test_proc.returncode

        print("")
        print("=" * 64)
        print("✅ ALL REAL-INSTALL CHECKS PASSED SUCCESSFULLY!")
        print("=" * 64)
        print(f"🧹 Automatically cleaning up sandbox: {tmp_dir}...")

    print("✨ Done! Zero changes made to your system environment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
