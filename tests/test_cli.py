import subprocess
import sys
import unittest
from pathlib import Path

# Ensure src/ is on sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from autodev.cli import (
    PROFILES,
    AgentState,
    get_safe_executable,
)


class TestCLIHelpers(unittest.TestCase):
    def test_get_safe_executable(self):
        """Existing system binaries must resolve, while nonexistent must return None."""
        self.assertIsNotNone(get_safe_executable("python3"))
        self.assertIsNone(get_safe_executable("nonexistent_binary_xyz_12345"))

    def test_agent_profiles(self):
        """Required default agent profiles must be configured with roles."""
        self.assertIn("agy", PROFILES)
        self.assertIn("opencode", PROFILES)
        self.assertIn("claude", PROFILES)
        self.assertIn("gemini", PROFILES)

        self.assertIn("plan", PROFILES["agy"].roles)
        self.assertIn("build", PROFILES["opencode"].roles)

    def test_agent_state_defaults(self):
        """AgentState must initialize with sensible defaults."""
        state = AgentState(plan_file=Path("PLAN.md"))
        self.assertEqual(state.max_retries, 3)
        self.assertFalse(state.auto_approve)
        self.assertEqual(state.permission_mode, "ask")

    def test_cli_help_flag(self):
        """Invoking the entry point with --help must exit with code 0."""
        res = subprocess.run(
            [sys.executable, "-m", "autodev.cli", "--help"],
            capture_output=True,
            text=True,
            cwd=str(ROOT_DIR),
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("SpeiiDev", res.stdout)
        self.assertIn("--font", res.stdout)

    def test_cli_font_flag(self):
        """Invoking with --font should render ASCII text and exit with 0."""
        res = subprocess.run(
            [sys.executable, "-m", "autodev.cli", "--font", "TEST", "--font-style", "mini"],
            capture_output=True,
            text=True,
            cwd=str(ROOT_DIR),
        )
        self.assertEqual(res.returncode, 0)
        self.assertTrue(len(res.stdout.strip()) > 0)

    def test_block_font_executable(self):
        """Running block-font runner script should exit with 0."""
        block_font_script = ROOT_DIR / "block-font"
        if block_font_script.exists():
            res = subprocess.run(
                [sys.executable, str(block_font_script), "OK"],
                capture_output=True,
                text=True,
                cwd=str(ROOT_DIR),
            )
            self.assertEqual(res.returncode, 0)
            self.assertIn("█", res.stdout)


if __name__ == "__main__":
    unittest.main()
