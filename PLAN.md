# Implementation Plan: Say Hi Feature for SpeiiDev

Phased implementation plan for adding the `say hi` feature to `autodev-orchestrator` (SpeiiDev).

## Goal Description
Implement an interactive and CLI greeting feature (`say hi` / `hi`) for SpeiiDev (`autodev`).
This feature enables users to say hi both in non-interactive batch/scripting mode and interactively in the REPL:
1. A dedicated greeting utility module (`/Users/mac/Documents/AI/autodev/src/autodev/hi.py`) with Catppuccin Bok Choy styling and ASCII / 3D block typography.
2. A CLI flag `--hi [NAME]` allowing users to print a greeting banner and exit cleanly.
3. An interactive REPL slash command `/hi [NAME]` providing friendly greeting banners and mascot artwork within the TUI.
4. Comprehensive unit and integration test coverage and updated documentation.

```mermaid
flowchart TD
    User([User / Shell]) --> ModeCheck{Invocation Mode}
    ModeCheck -->|CLI flag: --hi [NAME]| CLIRunner["/Users/mac/Documents/AI/autodev/src/autodev/cli.py:main()"]
    ModeCheck -->|REPL command: /hi [NAME]| REPLRunner["/Users/mac/Documents/AI/autodev/src/autodev/cli.py:interactive_repl()"]
    
    CLIRunner --> HiHandler["/Users/mac/Documents/AI/autodev/src/autodev/cli.py:handle_hi()"]
    REPLRunner --> HiHandler
    
    HiHandler --> CorePrint["/Users/mac/Documents/AI/autodev/src/autodev/hi.py:print_hi()"]
    CorePrint --> CoreFormat["/Users/mac/Documents/AI/autodev/src/autodev/hi.py:get_hi_greeting()"]
    CoreFormat --> BlockFont["/Users/mac/Documents/AI/autodev/src/autodev/font.py:render_block_text()"]
    CorePrint --> ConsoleOutput([Rich Console Rendered Banner])
```

---

## User Review Required
> [!NOTE]
> No breaking changes are introduced. All existing CLI flags, slash commands, configurations, and test suites will remain fully backwards-compatible.

---

## Open Questions
*None* — Requirements are well-defined and integrate cleanly into the existing modular CLI architecture.

---

## Proposed Changes

### Core Greeting Component

#### [NEW] `/Users/mac/Documents/AI/autodev/src/autodev/hi.py`
Exact Path: `/Users/mac/Documents/AI/autodev/src/autodev/hi.py`
Provides formatting and rendering routines for stylized "say hi" greetings.
- **Interface Signatures**:
  ```python
  from __future__ import annotations
  from typing import Optional
  from rich.console import Console

  def get_hi_greeting(name: str = "World", style: str = "claude") -> str:
      """Generate a stylized 'HI' greeting string with block font art.

      Args:
          name: The recipient name to greet (default: 'World').
          style: The typography style ('claude' for 3D shadow or 'mini' for 2-line).

      Returns:
          Formatted greeting text containing block art typography.
      """
      ...

  def print_hi(
      name: str = "World",
      style: str = "claude",
      console: Optional[Console] = None,
  ) -> None:
      """Render the 'HI' greeting inside a Rich Panel with Bok Choy Green accent.

      Args:
          name: The recipient name to greet (default: 'World').
          style: The typography style ('claude' or 'mini').
          console: Optional Rich Console instance (defaults to global Console()).
      """
      ...

  def say_hi(name: str = "World", style: str = "claude") -> None:
      """Top-level convenience entry point to say hi.

      Args:
          name: The recipient name to greet (default: 'World').
          style: The typography style ('claude' or 'mini').
      """
      ...
  ```

#### [MODIFY] `/Users/mac/Documents/AI/autodev/src/autodev/__init__.py`
Exact Path: `/Users/mac/Documents/AI/autodev/src/autodev/__init__.py`
Export public symbols `get_hi_greeting`, `print_hi`, and `say_hi`.
- **Interface Signatures**:
  ```python
  from autodev.hi import get_hi_greeting, print_hi, say_hi

  __all__ = [
      ...,
      "get_hi_greeting",
      "print_hi",
      "say_hi",
  ]
  ```

---

### CLI & TUI Integration

#### [MODIFY] `/Users/mac/Documents/AI/autodev/src/autodev/cli.py`
Exact Path: `/Users/mac/Documents/AI/autodev/src/autodev/cli.py`
- **Interface Signatures & Additions**:
  ```python
  # 1. Update SLASH_COMMANDS list:
  SLASH_COMMANDS: list[str] = [
      ...,
      "/hi",
      "/font",
      "/clear",
      "/help",
      "/exit",
  ]

  # 2. Add handler function:
  def handle_hi(state: AgentState, arg: str = "") -> None:
      """Handle the /hi slash command in the interactive REPL.

      Args:
          state: Current AgentState instance.
          arg: Optional argument containing recipient name (defaults to 'World').
      """
      ...

  # 3. Add argument in main() -> int:
  parser.add_argument(
      "--hi",
      nargs="?",
      const="World",
      default=None,
      metavar="NAME",
      help="Say hi with a stylized greeting banner and exit",
  )

  # 4. Add slash command dispatch in interactive_repl(state: AgentState) -> int:
  elif user_input.startswith("/hi"):
      parts = user_input.split(maxsplit=1)
      name_arg = parts[1].strip() if len(parts) > 1 else "World"
      handle_hi(state, name_arg)

  # 5. Add /hi row in show_help() -> None:
  table.add_row("/hi [name]", "Say hi with a stylized greeting banner")
  ```

---

### Test Suite

#### [NEW] `/Users/mac/Documents/AI/autodev/tests/test_hi.py`
Exact Path: `/Users/mac/Documents/AI/autodev/tests/test_hi.py`
Unit tests for `autodev.hi`.
- **Interface Signatures**:
  ```python
  import unittest

  class TestHi(unittest.TestCase):
      def test_default_greeting(self) -> None:
          """Test get_hi_greeting() returns default greeting for 'World'."""
          ...

      def test_custom_name_greeting(self) -> None:
          """Test get_hi_greeting('SpeiiDev') includes the target name."""
          ...

      def test_mini_font_style(self) -> None:
          """Test get_hi_greeting with style='mini'."""
          ...

      def test_print_hi_panel(self) -> None:
          """Test print_hi renders without exception to a captured Console."""
          ...

      def test_say_hi_convenience(self) -> None:
          """Test say_hi convenience wrapper executes cleanly."""
          ...
  ```

#### [MODIFY] `/Users/mac/Documents/AI/autodev/tests/test_cli.py`
Exact Path: `/Users/mac/Documents/AI/autodev/tests/test_cli.py`
Integration test cases added to `TestCLIHelpers`:
- **Interface Signatures**:
  ```python
  class TestCLIHelpers(unittest.TestCase):
      ...
      def test_cli_hi_flag(self) -> None:
          """Invoking --hi must exit 0 and print greeting."""
          ...

      def test_cli_hi_custom_name(self) -> None:
          """Invoking --hi 'Developer' must include 'Developer' in stdout."""
          ...

      def test_slash_command_hi_registered(self) -> None:
          """Ensure '/hi' is present in SLASH_COMMANDS."""
          ...
  ```

---

### Documentation

#### [MODIFY] `/Users/mac/Documents/AI/autodev/README.md`
Exact Path: `/Users/mac/Documents/AI/autodev/README.md`
- Document `/hi [name]` in the Interactive Slash Commands table.
- Document `--hi [NAME]` in the CLI Options section.

---

## Phased Implementation Plan

### Phase 1: Core Greeting Module
- [ ] 1.1 Create `/Users/mac/Documents/AI/autodev/src/autodev/hi.py` implementing `get_hi_greeting(name: str = "World", style: str = "claude") -> str`, `print_hi(name: str = "World", style: str = "claude", console: Optional[Console] = None) -> None`, and `say_hi(name: str = "World", style: str = "claude") -> None`.
- [ ] 1.2 Export `get_hi_greeting`, `print_hi`, and `say_hi` in `/Users/mac/Documents/AI/autodev/src/autodev/__init__.py` and include them in `__all__`.

**Verification Command**:
```bash
PYTHONPATH=src ./venv/bin/python3 -c "from autodev import get_hi_greeting, print_hi, say_hi; print(get_hi_greeting('World'))"
```

---

### Phase 2: CLI & Slash Command Dispatch
- [ ] 2.1 Add `"/hi"` to `SLASH_COMMANDS` list in `/Users/mac/Documents/AI/autodev/src/autodev/cli.py`.
- [ ] 2.2 Add `handle_hi(state: AgentState, arg: str = "") -> None` handler function in `/Users/mac/Documents/AI/autodev/src/autodev/cli.py`.
- [ ] 2.3 Add `--hi` flag (`nargs="?", const="World", default=None, metavar="NAME"`) in `parser.add_argument` within `main()` in `/Users/mac/Documents/AI/autodev/src/autodev/cli.py`.
- [ ] 2.4 Add execution handler in `main()` for `args.hi is not None` to call `print_hi(args.hi, style=args.font_style)` and return 0.
- [ ] 2.5 Add `/hi` handling in the REPL command loop in `interactive_repl()` in `/Users/mac/Documents/AI/autodev/src/autodev/cli.py`.
- [ ] 2.6 Add `/hi [name]` entry to `show_help()` table in `/Users/mac/Documents/AI/autodev/src/autodev/cli.py`.

**Verification Commands**:
```bash
PYTHONPATH=src ./venv/bin/python3 -m autodev.cli --help | grep -E "(--hi|hi)"
PYTHONPATH=src ./venv/bin/python3 -m autodev.cli --hi "SpeiiDev"
```

---

### Phase 3: Unit and Integration Tests
- [ ] 3.1 Implement unit tests in `/Users/mac/Documents/AI/autodev/tests/test_hi.py` testing `get_hi_greeting` (default name, custom name, styles), `print_hi`, and `say_hi`.
- [ ] 3.2 Add test cases `test_cli_hi_flag`, `test_cli_hi_custom_name`, and `test_slash_command_hi_registered` to `TestCLIHelpers` in `/Users/mac/Documents/AI/autodev/tests/test_cli.py`.
- [ ] 3.3 Execute unit and integration tests to confirm zero regressions.

**Verification Commands**:
```bash
PYTHONPATH=src ./venv/bin/pytest tests/test_hi.py -v
PYTHONPATH=src ./venv/bin/pytest tests/test_cli.py -k "hi" -v
PYTHONPATH=src ./venv/bin/pytest
```

---

### Phase 4: Documentation & Final Verification
- [ ] 4.1 Update `/Users/mac/Documents/AI/autodev/README.md` with `/hi` slash command description and `--hi` CLI flag documentation.
- [ ] 4.2 Run end-to-end regression testing and git status verification.

**Verification Commands**:
```bash
PYTHONPATH=src ./venv/bin/pytest
git diff --stat
```

---

## Verification Plan

### Automated Tests
Run full test suite via pytest:
```bash
PYTHONPATH=src ./venv/bin/pytest -v
```

### Manual Verification
1. Test CLI execution:
   ```bash
   PYTHONPATH=src ./venv/bin/python3 -m autodev.cli --hi "Pair Programmer"
   ```
2. Verify output displays:
   - TrueColor Bok Choy banner
   - Styled block font greeting "HI"
   - Friendly greeting message: "Hi, Pair Programmer! Welcome to SpeiiDev."
3. Test interactive REPL slash command:
   ```bash
   echo -e "/hi Alice\n/exit" | PYTHONPATH=src ./venv/bin/python3 -m autodev.cli --no-splash
   ```
