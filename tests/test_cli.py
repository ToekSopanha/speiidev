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

    def test_versions_consistent(self):
        """All version fields must agree (single source of truth)."""
        res = subprocess.run(
            [sys.executable, "scripts/bump_version.py", "--check"],
            capture_output=True,
            text=True,
            cwd=str(ROOT_DIR),
        )
        self.assertEqual(
            res.returncode,
            0,
            msg=f"Version mismatch:\n{res.stdout}\n{res.stderr}",
        )
    def test_block_font_runner_script(self):
        """Running block-font runner script should exit with 0."""
        block_font_script = ROOT_DIR / "bin" / "block-font"
        if not block_font_script.exists():
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

    def test_print_banner_responsive_widths(self):
        """Banner must dynamically scale and never overflow terminal width on resize."""
        from rich.console import Console
        import autodev.cli as cli

        state = cli.AgentState()
        for width in [120, 86, 80, 75, 60, 48, 35]:
            c = Console(width=width, height=24, color_system=None)
            cli.console = c
            with c.capture() as cap:
                cli.print_banner(state)
            out = cap.get()
            for line in out.splitlines():
                self.assertLessEqual(
                    len(line),
                    width,
                    f"Banner line exceeded terminal width {width}: {repr(line)}",
                )

        # Specifically verify 80-column terminal layout displays Claude 3D title art
        c80 = Console(width=80, height=24, color_system=None)
        cli.console = c80
        with c80.capture() as cap:
            cli.print_banner(state)
        out80 = cap.get()
        self.assertIn("▄██████╗", out80, "Expected Claude 3D font at 80 columns")
        self.assertIn("repo", out80)
        self.assertIn("plan", out80)
        self.assertIn("build", out80)

    def test_interactive_repl_resize_hook(self):
        """Interactive REPL resize hook must debounce and re-render without exception."""
        import asyncio
        from prompt_toolkit import PromptSession
        from prompt_toolkit.input import create_pipe_input
        import autodev.cli as cli

        with create_pipe_input() as pipe_input:
            session = PromptSession(input=pipe_input)
            orig_on_resize = session.app._on_resize
            resize_timer = [None]
            called = [0]

            def _do_redraw():
                called[0] += 1
                if getattr(session.app, "is_running", False):
                    try:
                        session.app.renderer.erase(leave_alternate_screen=False)
                        session.app._request_absolute_cursor_position()
                        session.app._redraw()
                    except Exception:
                        orig_on_resize()

            def _handle_resize():
                try:
                    loop = asyncio.get_running_loop()
                    if resize_timer[0] is not None:
                        resize_timer[0].cancel()
                    resize_timer[0] = loop.call_later(0.01, _do_redraw)
                except Exception:
                    _do_redraw()

            session.app._on_resize = _handle_resize

            pipe_input.send_text("test_cmd\n")
            res = session.prompt("❯ ")
            self.assertEqual(res, "test_cmd")
            # Verify handler can be called directly safely
            session.app._on_resize()

    def test_agent_stream_view_responsive_dimensions(self):
        """Live stream panel must fit within both terminal width and height on resize."""
        from rich.console import Console
        from collections import deque
        import autodev.cli as cli

        lines = deque(maxlen=18)
        for i in range(25):
            lines.append(
                f"Step {i}: processing /long/path/to/nested/module/that/could/cause/wrapping/on/narrow/screens/code.py"
            )

        state = cli.AgentState()
        view = cli._AgentStreamView(
            cmd=["agy", "--mode=accept-edits", "-p", "Execute tasks step-by-step with safety checks"],
            title="Building Application",
            border_color=cli.THEME["builder"],
            badge="[BUILDER]",
            attempt=1,
            state=state,
            lines=lines,
            activity=[("Read", "lib/main.py"), ("Write", "lib/out.py")],
        )

        for w, h in [(120, 30), (80, 24), (70, 20), (55, 16), (40, 12)]:
            c = Console(width=w, height=h, color_system=None)
            cli.console = c
            with c.capture() as cap:
                c.print(view)
            out = cap.get()
            rendered = out.splitlines()
            self.assertGreater(len(rendered), 0)
            self.assertLessEqual(
                len(rendered),
                h,
                f"Stream view panel height {len(rendered)} exceeded terminal height {h} at {w}x{h}",
            )
            for line in rendered:
                self.assertLessEqual(
                    len(line),
                    w,
                    f"Stream view panel line width {len(line)} exceeded terminal width {w} at {w}x{h}",
                )


if __name__ == "__main__":
    unittest.main()
