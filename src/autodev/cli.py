#!/usr/bin/env python3
"""
SpeiiDev: Interactive Multi-Agent TUI with pluggable agents, model switcher,
diff gate and conversation memory.

Roles:
  planner / auditor  - the agent that writes PLAN.md and audits (read-only plan mode)
  builder            - the agent that implements code from PLAN.md

Any combination of supported CLIs (agy, gemini, claude, opencode) can be assigned
to each role. The first run asks which CLI to use for each role and remembers it.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame
from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from autodev.font import render_block_text
from autodev._version import __version__

console = Console()

APP_VERSION = __version__
VERIFIED_MARKER = "STATUS: VERIFIED"
FIXES_MARKER = "STATUS: NEEDS_FIXES"

# ---------------------------------------------------------------------------
# THEME (Catppuccin-inspired TrueColor palette with Bok Choy Green accent)
# ---------------------------------------------------------------------------
THEME = {
    "primary": "#a6e3a1",
    "accent": "#f5c2e7",
    "text": "#cdd6f4",
    "dim": "#6c7086",
    "architect": "#94e2d5",
    "builder": "#cba6f7",
    "auditor": "#f9e2af",
    "ok": "#a6e3a1",
    "warn": "#fab387",
    "err": "#f38ba8",
    "surface": "#1e1e2e",
}

# ---------------------------------------------------------------------------
# PERSISTENT SESSION STATE  (~/.config/speiidev or ~/.config/autodev)
# ---------------------------------------------------------------------------
_default_cfg_dir = Path.home() / ".config" / "speiidev"
if not _default_cfg_dir.exists() and (Path.home() / ".config" / "autodev").exists():
    _default_cfg_dir = Path.home() / ".config" / "autodev"

CONFIG_DIR = Path(
    os.environ.get(
        "SPEIIDEV_HOME",
        os.environ.get("AUTODEV_HOME", str(_default_cfg_dir)),
    )
)
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history"
REMBER_FILE = CONFIG_DIR / "speiidevrember.json"
REMBER_MAX = 5

PERSISTED_KEYS = (
    "planner",
    "builder",
    "planner_model",
    "builder_model",
    "planner_effort",
    "builder_effort",
    "permission_mode",
    "approved_actions",
)

SLASH_COMMANDS = [
    "/auto",
    "/agents",
    "/plan",
    "/build",
    "/audit",
    "/model",
    "/effort",
    "/perms",
    "/log",
    "/conv",
    "/rember",
    "/diff",
    "/show",
    "/font",
    "/clear",
    "/help",
    "/exit",
]


@dataclass
class FileChange:
    path: Path
    old_content: str | None
    new_content: str | None


@dataclass
class AgentState:
    plan_file: Path = Path("PLAN.md")
    max_retries: int = 3
    auto_approve: bool = False
    timeout_seconds: int = 900
    last_status: str = "IDLE"
    git_branch: str = field(default_factory=lambda: get_git_branch())
    conversation_id: str | None = None
    # Locally generated id identifying this terminal session's chat (not the
    # agent's own conversation uuid). Saved to speiidevrember.json on exit.
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    last_task: str = ""
    # Pluggable agent roles (keys into PROFILES)
    planner: str = "agy"
    builder: str = "opencode"
    planner_model: str = "default"
    builder_model: str = "default"
    planner_effort: str = "default"
    builder_effort: str = "default"
    # Command permission gate
    permission_mode: str = "ask"  # ask | auto | deny
    approved_actions: set[str] = field(default_factory=set)
    # Persistence toggle (--no-save)
    persist: bool = True
    # Background activity capture (not persisted)
    last_log: list[str] = field(default_factory=list)
    last_files: list[tuple[str, str]] = field(default_factory=list)
    last_log_path: str | None = None
    last_agent: str = ""

    def profile(self, role: str) -> "AgentProfile":
        key = self.planner if role == "plan" else self.builder
        return PROFILES.get(key, PROFILES["agy"])


def get_safe_executable(binary_name: str) -> str | None:
    """Find the executable path across macOS, Linux, and Windows.

    Automatically handles Windows .cmd, .bat, and .exe wrappers
    (e.g., opencode.cmd) if the bare name is not found directly by shutil.which.
    """
    found = shutil.which(binary_name)
    if found:
        return found

    if platform.system() == "Windows":
        pathext = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";")
        for ext in pathext:
            ext = ext.strip()
            if not ext:
                continue
            candidate = f"{binary_name}{ext}" if ext.startswith(".") else f"{binary_name}.{ext}"
            found = shutil.which(candidate)
            if found:
                return found
        for ext in (".cmd", ".exe", ".bat"):
            found = shutil.which(f"{binary_name}{ext}")
            if found:
                return found

    return None


def get_git_branch() -> str:
    try:
        git_bin = get_safe_executable("git") or "git"
        res = subprocess.run(
            [git_bin, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            shell=platform.system() == "Windows",
        )
        return res.stdout.strip()
    except Exception:
        return "no-git"


def load_config() -> dict:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return _migrate_config(data) if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_config(state: AgentState) -> None:
    if not state.persist:
        return
    data = {key: getattr(state, key) for key in PERSISTED_KEYS}
    data["approved_actions"] = sorted(state.approved_actions)
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(CONFIG_FILE)
    except OSError:
        pass


def _migrate_config(cfg: dict) -> dict:
    """Map legacy v3 keys onto the v4 role-based schema."""
    if not cfg:
        return cfg
    m = dict(cfg)
    m.setdefault("planner", "agy")
    m.setdefault("builder", "opencode")
    m.setdefault("planner_model", m.get("agy_model", "default"))
    m.setdefault("builder_model", m.get("opencode_model", "default"))
    m.setdefault("planner_effort", m.get("agy_effort", "default"))
    m.setdefault("builder_effort", m.get("opencode_variant", "default"))
    for key in ("planner_model", "builder_model"):
        if "default" in str(m.get(key, "")).lower():
            m[key] = "default"
    return m


# ---------------------------------------------------------------------------
# REMEMBERED CHATS  (~/.config/speiidev/speiidevrember.json)
# Old conversations are never resumed automatically. Every chat id is written
# here with a timestamp so it can be recalled explicitly via /rember.
# ---------------------------------------------------------------------------
def load_rember() -> list[dict]:
    try:
        data = json.loads(REMBER_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [e for e in data if isinstance(e, dict) and e.get("id")]
        if isinstance(data, dict) and data.get("id"):
            return [data]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


def save_rember(entries: list[dict]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = REMBER_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        tmp.replace(REMBER_FILE)
    except OSError:
        pass


def remember_conversation(conversation_id: str, label: str = "") -> None:
    """Record a conversation id + timestamp, newest first, de-duplicated by id."""
    if not conversation_id:
        return
    entry = {
        "id": conversation_id,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "label": label or f"chat {conversation_id[:8]}",
    }
    entries = [e for e in load_rember() if e.get("id") != conversation_id]
    entries.insert(0, entry)
    save_rember(entries[:REMBER_MAX])


def persist_active_chat(state: "AgentState") -> None:
    """Save this session's chat id to speiidevrember.json on tool exit.

    Uses the agent conversation uuid when one is set, otherwise the locally
    generated session id, so every session is always remembered.
    """
    chat_id = state.conversation_id or state.session_id
    label = state.last_task or state.last_agent or ""
    remember_conversation(chat_id, label)


# ============================================================================
# AGENT PROFILES  (pluggable CLI adapters)
# ============================================================================

def _is_default(value: str | None) -> bool:
    return not value or "default" in str(value).lower()


def _agy_plan(prompt, model, effort, allow_tools, plan_file, session_id):
    cmd = ["agy", "--mode=plan"]
    if session_id:
        cmd.append(f"--conversation={session_id}")
    if not _is_default(model):
        cmd.append(f"--model={model}")
    elif not _is_default(effort):
        cmd.append(f"--effort={effort}")
    if allow_tools:
        cmd.append("--dangerously-skip-permissions")
    cmd += ["-p", prompt]
    return cmd


def _agy_build(prompt, model, effort, allow_tools, plan_file, session_id):
    cmd = ["agy", "--mode=accept-edits"]
    if session_id:
        cmd.append(f"--conversation={session_id}")
    if not _is_default(model):
        cmd.append(f"--model={model}")
    elif not _is_default(effort):
        cmd.append(f"--effort={effort}")
    if allow_tools:
        cmd.append("--dangerously-skip-permissions")
    cmd += ["-p", prompt]
    return cmd


def _gemini_plan(prompt, model, effort, allow_tools, plan_file, session_id):
    cmd = ["gemini", "--approval-mode", "plan", "--skip-trust"]
    if not _is_default(model):
        cmd += ["-m", model]
    cmd += ["-p", prompt]
    return cmd


def _gemini_build(prompt, model, effort, allow_tools, plan_file, session_id):
    cmd = [
        "gemini",
        "--approval-mode",
        "yolo" if allow_tools else "auto_edit",
        "--skip-trust",
    ]
    if not _is_default(model):
        cmd += ["-m", model]
    cmd += ["-p", prompt]
    return cmd


def _claude_plan(prompt, model, effort, allow_tools, plan_file, session_id):
    cmd = ["claude", "-p", "--permission-mode", "plan"]
    if not _is_default(model):
        cmd += ["--model", model]
    if not _is_default(effort):
        cmd += ["--effort", effort]
    cmd.append(prompt)
    return cmd


def _claude_build(prompt, model, effort, allow_tools, plan_file, session_id):
    cmd = ["claude", "-p", "--permission-mode", "acceptEdits"]
    if allow_tools:
        cmd.append("--dangerously-skip-permissions")
    if not _is_default(model):
        cmd += ["--model", model]
    if not _is_default(effort):
        cmd += ["--effort", effort]
    cmd.append(prompt)
    return cmd


def _opencode_build(prompt, model, effort, allow_tools, plan_file, session_id):
    cmd = ["opencode", "run"]
    if not _is_default(model):
        cmd += ["--model", model]
    if not _is_default(effort):
        cmd += ["--variant", effort]
    if allow_tools:
        cmd.append("--auto")
    cmd += ["--agent", "build"]
    # NOTE: --file is a greedy yargs array option; it consumes every following
    # positional. The message MUST come before it, otherwise the prompt is
    # parsed as a filename ("File not found: <prompt>").
    cmd.append(prompt)
    if plan_file:
        cmd += ["--file", str(plan_file)]
    return cmd


@dataclass
class AgentProfile:
    key: str
    label: str
    binary: str
    blurb: str
    roles: tuple[str, ...]  # subset of ("plan", "build")
    efforts: tuple[str, ...]
    plan_builder: Callable[..., list[str]] | None
    build_builder: Callable[..., list[str]] | None
    models_cmd: tuple[str, ...] | None = None

    def build(self, role, prompt, model, effort, allow_tools, plan_file, session_id):
        builder = self.plan_builder if role == "plan" else self.build_builder
        if builder is None:
            # Auto-fallback to a profile that can serve this role (prefer installed ones)
            candidates = installed_for_role(role)
            if candidates:
                fallback = candidates[0]
                fb = PROFILES[fallback]
                builder_fb = fb.plan_builder if role == "plan" else fb.build_builder
                if builder_fb is not None:
                    return builder_fb(prompt, model, effort, allow_tools, plan_file, session_id)
            raise ValueError(f"{self.label} cannot act as {role}")
        return builder(prompt, model, effort, allow_tools, plan_file, session_id)


PROFILES: dict[str, AgentProfile] = {
    "agy": AgentProfile(
        "agy", "agy", "agy",
        "Google Antigravity — strong planner, auditor & builder",
        ("plan", "build"),
        ("default", "low", "medium", "high", "xhigh", "max"),
        _agy_plan, _agy_build, ("agy", "models"),
    ),
    "opencode": AgentProfile(
        "opencode", "opencode", "opencode",
        "OpenCode — general-purpose coding builder",
        ("build",),
        ("default", "minimal", "low", "medium", "high", "max"),
        None, _opencode_build, ("opencode", "models"),
    ),
    "gemini": AgentProfile(
        "gemini", "gemini", "gemini",
        "Google Gemini CLI — read-only plan mode & yolo builder",
        ("plan", "build"),
        ("default",),
        _gemini_plan, _gemini_build, None,
    ),
    "claude": AgentProfile(
        "claude", "claude", "claude",
        "Anthropic Claude Code — plan mode & accept-edits builder",
        ("plan", "build"),
        ("default", "low", "medium", "high", "max"),
        _claude_plan, _claude_build, None,
    ),
}


def installed_profiles() -> list[str]:
    return [key for key, prof in PROFILES.items() if get_safe_executable(prof.binary)]


def installed_for_role(role: str) -> list[str]:
    """Installed agent CLIs on this PC that can serve a role ("plan"/"build")."""
    return [k for k in installed_profiles() if role in PROFILES[k].roles]


def first_installed_for(role: str) -> str | None:
    found = installed_profiles()
    for key in found:
        return key
    return None


def _preview_cmd(cmd: list[str]) -> str:
    parts: list[str] = []
    for item in cmd:
        if len(item) > 64:
            parts.append(item[:61] + "…")
        elif " " in item:
            parts.append(f'"{item}"')
        else:
            parts.append(item)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# BACKGROUND ACTIVITY PARSER
#   Turns raw agent streams ("→ Read lib/foo.dart") into "● Read(/abs/path)"
#   so the user can see exactly which files the agent touched.
# ---------------------------------------------------------------------------
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_FILE_ACTIONS = {"Read", "Write", "Edit", "Create", "Delete", "Move", "Patch"}
_SEARCH_ACTIONS = {"Glob", "Grep", "Search", "List", "Find"}
_TOOL_RE = re.compile(
    r"^[\s\u2500-\u27bf\u2190-\u21ff\u2600-\u26ff]*"
    r"([\u2192\u2190\u2731\u273e\u273f\u2726\u2717\u2699$\u203a>])?\s*"
    r"(Read|Write|Edit|Create|Delete|Move|Patch|Glob|Grep|Search|List|Find|"
    r"Bash|Run|Exec|Fetch|Task|WebFetch|WebSearch)\b\s*(.*)$",
    re.IGNORECASE,
)
_PAREN_RE = re.compile(
    r"\b(Read|Write|Edit|Create|Delete|Move|Patch|Glob|Grep|Search|List|Find|"
    r"Bash|Run|Exec|Fetch|Task)\s*\(([^)]*)\)",
    re.IGNORECASE,
)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _shorten_path(path_str: str) -> str:
    try:
        home = Path.home()
        p = Path(path_str)
        rel = p.relative_to(home)
        return str(Path("~") / rel)
    except (ValueError, OSError):
        return path_str


def _resolve_path(token: str) -> str:
    token = token.strip().strip('"\'').rstrip(",;:)]}").strip()
    if not token or token in ("-", "…"):
        return token
    p = Path(os.path.expanduser(token))
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        p = p.resolve()
    except OSError:
        return _shorten_path(str(p))
    return _shorten_path(str(p))


def _parse_action(raw: str) -> tuple[str, str] | None:
    line = _strip_ansi(raw).strip()
    if not line:
        return None
    if line.startswith("$"):
        return ("Bash", line[1:].strip())
    m = _PAREN_RE.search(line)
    if m:
        return (m.group(1).capitalize(), m.group(2).strip())
    m = _TOOL_RE.match(line)
    if m:
        sym, tool, rest = m.group(1), m.group(2), m.group(3).strip()
        tool = tool.capitalize()
        if sym == "$" or tool in ("Run", "Exec"):
            return ("Bash", (rest or line).strip())
        return (tool, rest)
    return None


def _fmt_activity(raw: str) -> str:
    act = _parse_action(raw)
    if not act:
        return _strip_ansi(raw).rstrip()
    action, arg = act
    arg = arg.strip()
    if action in _FILE_ACTIONS:
        token = arg.split()[0] if arg.split() else arg
        shown = _resolve_path(token)
    elif action in _SEARCH_ACTIONS:
        m = re.search(r'"([^"]+)"|\'([^\']+)\'', arg)
        if m:
            shown = m.group(1) or m.group(2)
        else:
            shown = arg.split()[0] if arg.split() else arg
    else:
        shown = arg
    return f"● {action}({shown})"


def _action_target(action: str, arg: str) -> str | None:
    arg = arg.strip()
    if action in _FILE_ACTIONS:
        token = arg.split()[0] if arg.split() else arg
        return _resolve_path(token)
    if action in _SEARCH_ACTIONS:
        m = re.search(r'"([^"]+)"|\'([^\']+)\'', arg)
        if m:
            return m.group(1) or m.group(2)
        return arg.split()[0] if arg.split() else "(search)"
    if action == "Bash":
        return arg
    return None


def parse_background_activity(lines: list[str]) -> list[tuple[str, str]]:
    """Extract (action, target) pairs for files the agent touched."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for raw in lines:
        act = _parse_action(raw)
        if not act:
            continue
        target = _action_target(act[0], act[1])
        if target is None:
            continue
        key = (act[0], target)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _write_run_log(label: str, lines: list[str]) -> str | None:
    try:
        log_dir = CONFIG_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        digest = re.sub(r"[^A-Za-z0-9._-]+", "-", label or "run")[:40]
        path = log_dir / f"{ts}-{digest}.log"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path)
    except OSError:
        return None


# ============================================================================
# SNAPSHOT & COLOR-CODED DIFF APPROVAL ENGINE
# ============================================================================

def take_workspace_snapshot(exclude: set[Path] | None = None) -> dict[Path, str]:
    exclude = exclude or set()
    snapshot: dict[Path, str] = {}

    try:
        git_bin = get_safe_executable("git") or "git"
        res = subprocess.run(
            [git_bin, "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            check=True,
            shell=platform.system() == "Windows",
        )
        rel_paths = [Path(p) for p in res.stdout.splitlines() if p.strip()]
    except Exception:
        rel_paths = [
            p.relative_to(Path.cwd())
            for p in Path.cwd().rglob("*")
            if p.is_file() and ".git" not in p.parts
        ]

    for rel_path in rel_paths:
        if rel_path in exclude or not rel_path.is_file():
            continue
        try:
            snapshot[rel_path] = rel_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError, OSError):
            continue

    return snapshot


def compute_workspace_changes(
    before: dict[Path, str], exclude: set[Path] | None = None
) -> list[FileChange]:
    after = take_workspace_snapshot(exclude=exclude)
    all_paths = sorted(set(before.keys()) | set(after.keys()))
    changes: list[FileChange] = []

    for path in all_paths:
        old_text = before.get(path)
        new_text = after.get(path)
        if old_text != new_text:
            changes.append(FileChange(path=path, old_content=old_text, new_content=new_text))

    return changes


def render_colored_diff_panel(change: FileChange) -> Panel:
    old_lines = (change.old_content or "").splitlines()
    new_lines = (change.new_content or "").splitlines()

    if change.old_content is None:
        badge = "[bold black on bright_green] NEW FILE [/bold black on bright_green]"
    elif change.new_content is None:
        badge = "[bold white on red] DELETED [/bold white on red]"
    else:
        badge = "[bold black on yellow] MODIFIED [/bold black on yellow]"

    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{change.path} (OLD)",
            tofile=f"b/{change.path} (NEW)",
            lineterm="",
            n=3,
        )
    )

    added_count = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    removed_count = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))

    diff_text = Text()
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---"):
            diff_text.append(f"{line}\n", style="bold dim")
        elif line.startswith("@@"):
            diff_text.append(f"{line}\n", style="bold cyan")
        elif line.startswith("+"):
            diff_text.append(" + ", style="bold bright_green on #113311")
            diff_text.append(f"{line[1:]}\n", style="bright_green on #113311")
        elif line.startswith("-"):
            diff_text.append(" - ", style="bold bright_red on #3b1219")
            diff_text.append(f"{line[1:]}\n", style="bright_red on #3b1219")
        else:
            diff_text.append(f"   {line[1:] if line.startswith(' ') else line}\n", style="dim white")

    title = (
        f"{badge} [bold white]{change.path}[/bold white]  "
        f"[bold bright_green]+{added_count} new[/bold bright_green]  "
        f"[bold bright_red]-{removed_count} old[/bold bright_red]"
    )

    w = console.width
    pad_h = 2 if w >= 80 else 1
    if w >= 65:
        legend = Text.from_markup(
            "[bold bright_green on #113311] + Green = New Code Added [/bold bright_green on #113311]   "
            "[bold bright_red on #3b1219] - Red = Old Code Removed [/bold bright_red on #3b1219]"
        )
    else:
        legend = Text.from_markup("[green]+ New Code[/green]  [red]- Old Code[/red]")

    return Panel(
        Group(legend, Rule(style="dim"), diff_text),
        title=title,
        title_align="left",
        border_style="bright_magenta",
        box=box.ROUNDED,
        padding=(0, pad_h),
    )


def review_and_approve_changes(changes: list[FileChange], auto_approve: bool = False) -> None:
    if not changes:
        console.print("[dim]No application source files were modified in this pass.[/dim]")
        return

    console.print(
        f"\n[bold {THEME['builder']}]🔍 Builder modified {len(changes)} file(s). "
        f"Review changes below:[/]\n"
    )

    accept_all = auto_approve
    for idx, change in enumerate(changes, start=1):
        console.print(render_colored_diff_panel(change))

        if accept_all:
            console.print(f"  [bold green]✓ Auto-applied ({idx}/{len(changes)}):[/bold green] {change.path}")
            continue

        console.print(
            f"  [bold white]({idx}/{len(changes)}) Apply changes to [cyan]{change.path}[/cyan]?[/bold white] "
            "[bold green][Enter = Allow][/bold green] / "
            "[bold red][n = Reject & Revert][/bold red] / "
            "[bold yellow][a = Allow All][/bold yellow]: ",
            end="",
        )
        try:
            choice = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = "n"

        if choice == "a":
            accept_all = True
            console.print(f"  [bold green]✓ Allowed {change.path} (and all remaining files)[/bold green]")
        elif choice in ("", "y", "yes"):
            console.print(f"  [bold green]✓ Allowed changes to {change.path}[/bold green]")
        else:
            if change.old_content is None:
                change.path.unlink(missing_ok=True)
            else:
                change.path.write_text(change.old_content, encoding="utf-8")
            console.print(
                f"  [bold red]↩ Reverted {change.path} back to original code![/bold red]"
            )


# ============================================================================
# COMMAND PERMISSION GATE  (allow / deny / allow-always)
# ============================================================================

def arrow_menu(
    title: str,
    options: list[tuple[str, str]],
    text: str = "",
    default: str | None = None,
):
    """Arrow-key selection menu (↑/↓ move, Enter select, Esc cancel).

    options: list of (value, label). Returns the chosen value, or None if
    cancelled / unavailable (non-interactive), so callers can fall back.
    Renders with the same searchable picker used for model selection.
    """
    return searchable_select(
        title,
        options,
        current=default,
        mark_current=False,
        footer="↑/↓ Navigate   ·   Enter select   ·   Esc cancel",
        height=min(10, max(1, len(options))),
    )


def searchable_select(
    title: str,
    options: list[tuple[str, str]],
    current: str | None = None,
    prompt_label: str = "Search:",
    footer: str = "↑/↓ Navigate   Enter Select   Esc Go Back",
    height: int = 12,
    mark_current: bool = True,
):
    """Type-to-filter picker styled after opencode's model selector.

    options: list of (value, label). Returns the chosen value, or None when
    cancelled / unavailable (non-interactive). The item matching ``current``
    is pre-highlighted, and marked ``(current)`` when ``mark_current``.
    """
    if not console.is_terminal or not options:
        return None

    values = [v for v, _ in options]
    st = {"query": "", "sel": 0, "results": list(range(len(options)))}
    if current is not None and current in values:
        st["sel"] = values.index(current)

    def get_dynamic_height() -> int:
        term_lines = shutil.get_terminal_size((80, 24)).lines
        max_h = max(2, term_lines - 7)
        return min(height, max_h, max(1, len(options)))

    def recompute(reset: bool = True) -> None:
        q = st["query"].strip().lower()
        if not q:
            st["results"] = list(range(len(options)))
        else:
            st["results"] = [
                i
                for i, (v, label) in enumerate(options)
                if q in v.lower() or q in label.lower()
            ]
        if reset:
            st["sel"] = 0
        if st["sel"] >= len(st["results"]):
            st["sel"] = max(0, len(st["results"]) - 1)

    def current_value() -> str | None:
        if not st["results"]:
            return None
        return options[st["results"][st["sel"]]][0]

    def search_text():
        return [
            ("class:prompt", f"  {prompt_label} "),
            ("class:query", st["query"]),
        ]

    def list_text():
        res = st["results"]
        if not res:
            return [("class:dim", "  (no matches)")]
        win = get_dynamic_height()
        start = 0
        if st["sel"] >= win:
            start = st["sel"] - win + 1
        end = min(len(res), start + win)
        term_cols = shutil.get_terminal_size((80, 24)).columns
        max_label_w = max(10, term_cols - 14)
        lines = []
        for pos in range(start, end):
            value, label = options[res[pos]]
            is_sel = pos == st["sel"]
            is_cur = mark_current and current is not None and value == current
            mark = "  (current)" if is_cur else ""
            cursor = "> " if is_sel else "  "
            cls = "sel" if is_sel else ("current" if is_cur else "item")
            disp = label
            if len(disp) + len(mark) > max_label_w:
                disp = disp[: max(1, max_label_w - len(mark) - 1)] + "…"
            lines.append((f"class:{cls}", f"{cursor}{disp}{mark}\n"))
        return lines

    def status_text():
        n = len(st["results"])
        pos = (st["sel"] + 1) if n else 0
        return [("class:dim", f"  {pos}/{n}")]

    def footer_text():
        term_cols = shutil.get_terminal_size((80, 24)).columns
        if term_cols < 55:
            return [("class:footer", "  ↑/↓ Enter Esc")]
        return [("class:footer", f"  Keyboard: {footer}")]

    style = Style.from_dict(
        {
            "frame.border": THEME["primary"],
            "frame.label": f"bold {THEME['primary']}",
            "prompt": f"bold {THEME['primary']}",
            "query": THEME["text"],
            "item": THEME["text"],
            "current": THEME["ok"],
            "sel": f"bold {THEME['surface']} bg:{THEME['accent']}",
            "dim": THEME["dim"],
            "footer": THEME["dim"],
            "sep": THEME["dim"],
        }
    )

    search_window = Window(
        FormattedTextControl(search_text, focusable=True), height=1
    )
    body = HSplit(
        [
            search_window,
            Window(char="─", height=1, style="class:sep"),
            Window(
                FormattedTextControl(list_text),
                height=get_dynamic_height,
            ),
            Window(FormattedTextControl(status_text), height=1),
            Window(FormattedTextControl(footer_text), height=1),
        ]
    )
    layout = Layout(Frame(body, title=title), focused_element=search_window)

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("c-p")
    def _(event):
        if st["results"]:
            st["sel"] = (st["sel"] - 1) % len(st["results"])
        event.app.invalidate()

    @kb.add("down")
    @kb.add("c-n")
    def _(event):
        if st["results"]:
            st["sel"] = (st["sel"] + 1) % len(st["results"])
        event.app.invalidate()

    @kb.add("pageup")
    def _(event):
        win = get_dynamic_height()
        if st["results"]:
            st["sel"] = max(0, st["sel"] - win)
        event.app.invalidate()

    @kb.add("pagedown")
    def _(event):
        win = get_dynamic_height()
        if st["results"]:
            st["sel"] = min(len(st["results"]) - 1, st["sel"] + win)
        event.app.invalidate()

    @kb.add("enter")
    @kb.add("c-m")
    @kb.add("c-j")
    def _(event):
        event.app.exit(result=current_value())

    @kb.add("escape")
    @kb.add("c-c")
    @kb.add("c-q")
    def _(event):
        event.app.exit(result=None)

    @kb.add("backspace")
    def _(event):
        st["query"] = st["query"][:-1]
        recompute()
        event.app.invalidate()

    @kb.add("c-u")
    def _(event):
        st["query"] = ""
        recompute()
        event.app.invalidate()

    @kb.add(Keys.Any)
    def _(event):
        ch = event.data
        if ch and ch.isprintable():
            st["query"] += ch
            recompute()
            event.app.invalidate()

    try:
        return Application(
            layout=layout,
            key_bindings=kb,
            style=style,
            full_screen=False,
            mouse_support=False,
            terminal_size_polling_interval=0.5,
        ).run()
    except (EOFError, KeyboardInterrupt):
        return None
    except Exception:
        return None


def request_permission(
    state: AgentState, action_key: str, title: str, detail: str
) -> bool:
    """Gate a command about to run. Returns True if it may proceed."""
    if state.permission_mode == "deny":
        console.print(
            f"  [{THEME['err']}]⛔ blocked by DENY mode:[/] [{THEME['dim']}]{title}[/]\n"
        )
        return False

    if state.permission_mode == "auto" or action_key in state.approved_actions:
        console.print(
            f"  [{THEME['ok']}]✓ auto-approved[/] [{THEME['dim']}]{title}[/]\n"
        )
        return True

    body = Group(
        Text.from_markup(f"[bold {THEME['text']}]{detail}[/bold {THEME['text']}]"),
        Rule(style=THEME["dim"]),
        Text.from_markup(
            f"[{THEME['dim']}]Use arrow keys to choose, Enter to confirm.[/]"
        ),
    )
    w = console.width
    pad_h = 2 if w >= 80 else 1
    panel_title = (
        f"[bold {THEME['auditor']}]🔐 Permissions requested[/bold {THEME['auditor']}]  "
        f"[{THEME['dim']}]{title}[/]"
        if w >= 70
        else f"[bold {THEME['auditor']}]🔐 Permissions[/]"
    )
    console.print(
        Panel(
            body,
            title=panel_title,
            title_align="left",
            border_style=THEME["auditor"],
            box=box.ROUNDED,
            padding=(0, pad_h),
        )
    )

    choice = arrow_menu(
        "Permission required",
        [
            ("y", "✔  Allow once"),
            ("a", "✔  Allow always  (remember this action)"),
            ("n", "✖  Deny"),
        ],
        text=title,
        default="y",
    )

    if choice == "a":
        state.approved_actions.add(action_key)
        console.print(
            f"  [{THEME['ok']}]✓ allowed always[/] [{THEME['dim']}]({action_key} will not ask again this session)[/]\n"
        )
        return True
    if choice == "y":
        console.print(f"  [{THEME['ok']}]✓ allowed once[/]\n")
        return True
    console.print(f"  [{THEME['err']}]✗ denied[/]\n")
    return False


# ============================================================================
# TUI BANNER & STREAMING BOXES (WITH AUTO-RETRY)
# ============================================================================

def _mode_badge(mode: str) -> str:
    if mode == "auto":
        return "[bold #11111b on #a6e3a1] AUTO [/bold #11111b on #a6e3a1]"
    if mode == "deny":
        return "[bold white on #f38ba8] DENY [/bold white on #f38ba8]"
    return "[bold #11111b on #fab387] ASK [/bold #11111b on #fab387]"


# ---------------------------------------------------------------------------
# PIXEL ART GREEN BOK CHOY CABBAGE SPRITE & SPEIIDEV LOGO
# ---------------------------------------------------------------------------
BOK_CHOY_PALETTE: dict[str, str | None] = {
    ".": None,       # transparent background
    "#": "#1b261b",  # dark silhouette outline
    "D": "#3b6138",  # deep leaf green
    "G": "#548744",  # mid leaf green
    "M": "#7da367",  # bright leaf green
    "L": "#a2c488",  # pale leaf rib
    "S": "#d6e9bc",  # cream cabbage stem
    "W": "#f2f8e6",  # white stem highlight
}

BOK_CHOY_SPRITE = [
    "..........######..........",
    ".........#GGGDDD#..####...",
    "...####.#GDDDDDDD##GGGD#..",
    ".##GGDD#GDDDLDDLDD#DDDDD#.",
    ".#GGDGD#DDDDLDDLDD#DDDLD#.",
    "#GGGDD#GDLDDLDDLDDD#DLDDD#",
    "#GDDLD#GDLDDLDLDDDD#DDDDD#",
    "#GDDLD#GDDLDDLDDDLD#LDDLD#",
    "#GLLDL#GDDDLDSDDDLD#LDLDD#",
    "#GDLLL#GLDDDLSDDLDD#LLDDD#",
    "#GDDDL#GDLDDDSDLDDD#LDDDD#",
    "#GDLDDL#DDLDDSSDDD#LDDDD#.",
    ".#GDLDD#DDDSDSDDLD#DLLD#..",
    ".#GDDLL#GDDDSSDSDD#LDDD#..",
    "..#DDDDL#GDDSSSDD#LDDD#...",
    "...##DDDL#GDSSDD#LDDD#....",
    ".....#DDLL#DSSD#LLDD#.....",
    "......#DLS#LSSL#LLD#......",
    ".......#LS#SSSS#SL#.......",
    ".......#SSMSWSSMSL#.......",
    ".......#SSMSWSSMSS#.......",
    "......#LWMWWWWSSMSL#......",
    "......#LWMWWWWSSMSL#......",
    "......#LWMWWWWSSMSL#......",
    "......#LWMSWWWSSMSL#......",
    ".......#LSMWWWSMSSL#......",
    "........#LSMMMMSSL#.......",
    ".........##LLLLL##........",
    "...........#####..........",
    "..........................",
]

SPEIIDEV_ASCII = render_block_text("SPEIIDEV", style="claude", color="none")


def render_bok_choy_logo() -> Text:
    """Render the Pixel Art Green Bok Choy Cabbage as ANSI half-block characters."""
    text = Text()
    h = len(BOK_CHOY_SPRITE)
    w = len(BOK_CHOY_SPRITE[0])
    for r in range(0, h, 2):
        for col in range(w):
            top = BOK_CHOY_SPRITE[r][col]
            bot = BOK_CHOY_SPRITE[r + 1][col] if r + 1 < h else "."
            tc = BOK_CHOY_PALETTE.get(top)
            bc = BOK_CHOY_PALETTE.get(bot)
            if not tc and not bc:
                text.append(" ")
            elif tc and not bc:
                text.append("▀", style=tc)
            elif not tc and bc:
                text.append("▄", style=bc)
            else:
                text.append("▀", style=f"{tc} on {bc}")
        if r + 2 < h:
            text.append("\n")
    return text


def run_splash(state: AgentState) -> None:
    """Short, GIF-free ASCII boot animation. Skips when output is not a TTY."""
    if not console.is_terminal:
        return

    boot_steps = [
        ("booting orchestrator", "kernel"),
        ("linking architect", "agy · gemini"),
        ("linking builder", "opencode"),
        ("waking workspace", Path.cwd().name),
    ]

    try:
        with Live(
            console=console, refresh_per_second=24, transient=True
        ) as live:
            for idx, (label, tag) in enumerate(boot_steps, start=1):
                w = console.width
                h = console.size.height or 24

                # Responsive title typography
                if w >= 80:
                    art = render_block_text("SPEIIDEV", style="claude", color="none")
                    title_node = Text.from_markup(f"[bold {THEME['primary']}]{art}[/]")
                elif w >= 52:
                    art = render_block_text("SPEIIDEV", style="mini", color="none")
                    title_node = Text.from_markup(f"[bold {THEME['primary']}]{art}[/]")
                else:
                    title_node = Text.from_markup(
                        f"[bold {THEME['primary']}]SPEIIDEV[/bold {THEME['primary']}] "
                        f"[{THEME['dim']}]v{APP_VERSION}[/]"
                    )

                show_full_cabbage = (w >= 80 and h >= 22)
                bar_width = max(10, min(36, w - 46 if show_full_cabbage else w - 24))
                filled = int(bar_width * idx / len(boot_steps))
                bar = "█" * filled + "░" * (bar_width - filled)

                status_body = Group(
                    Text.from_markup(
                        f"[bold {THEME['primary']}]SPEIIDEV[/bold {THEME['primary']}] "
                        f"[{THEME['dim']}]v{APP_VERSION} · multi-agent orchestrator[/]"
                    ),
                    Rule(style=THEME["dim"]),
                    Text.from_markup(
                        f"  [{THEME['primary']}]{bar}[/] "
                        f"[{THEME['dim']}]{idx}/{len(boot_steps)}[/]"
                    ),
                    Text.from_markup(
                        f"  [{THEME['dim']}]{label}[/] "
                        f"[{THEME['architect']}]{tag}[/]"
                    ),
                )
                if h >= 20:
                    status_body = Group(
                        status_body,
                        Text.from_markup(
                            f"\n[{THEME['dim']}]Initializing neural coding environment…[/]"
                        ),
                    )

                if show_full_cabbage:
                    cabbage = render_bok_choy_logo()
                    status_grid = Table.grid(padding=(0, 2 if w < 86 else 3))
                    status_grid.add_column(justify="left")
                    status_grid.add_column(justify="left", ratio=1)
                    status_grid.add_row(cabbage, status_body)
                    splash_content = status_grid
                else:
                    splash_content = status_body

                body = Group(
                    title_node,
                    Rule(style=THEME["dim"]),
                    splash_content,
                )

                pad_h = 2 if w >= 86 else 1
                pad_v = 1 if (w >= 80 and h >= 22) else 0
                live.update(
                    Panel(
                        body,
                        box=box.ROUNDED,
                        border_style=THEME["primary"],
                        padding=(pad_v, pad_h),
                    )
                )
                time.sleep(0.24)
            time.sleep(0.12)
    except KeyboardInterrupt:
        pass


def print_banner(state: AgentState) -> None:
    w = console.width
    h = console.size.height or 24

    # 1. Responsive Title Art
    if w >= 80:
        art = render_block_text("SPEIIDEV", style="claude", color="none")
        title_renderable = Text.from_markup(f"[bold {THEME['primary']}]{art}[/]")
    elif w >= 52:
        art = render_block_text("SPEIIDEV", style="mini", color="none")
        title_renderable = Text.from_markup(f"[bold {THEME['primary']}]{art}[/]")
    else:
        title_renderable = Text.from_markup(
            f"[bold {THEME['primary']}]SPEIIDEV[/bold {THEME['primary']}] "
            f"[{THEME['dim']}]v{APP_VERSION}[/]"
        )

    # 2. Subtitle
    if w >= 60:
        sub = Text.from_markup(
            f"\n[bold {THEME['primary']}]SPEIIDEV[/bold {THEME['primary']}] "
            f"[{THEME['dim']}]v{APP_VERSION}[/{THEME['dim']}]  ·  "
            f"[bold {THEME['text']}]Autonomous Multi-Agent Orchestrator[/bold {THEME['text']}]"
        )
    else:
        sub = Text.from_markup(
            f"[bold {THEME['text']}]Autonomous Multi-Agent Orchestrator[/bold {THEME['text']}]"
        )

    banner_items: list = [title_renderable, sub, Rule(style=THEME["dim"])]

    # 3. Active conversation string
    active_chat = state.conversation_id or state.session_id
    conv_display = (
        f"[{THEME['ok']}]{active_chat[:8]}…[/{THEME['ok']}]"
        if state.conversation_id
        else f"[{THEME['dim']}]{active_chat[:8]}… (new)[/{THEME['dim']}]"
    )

    # 4. Mascot and Workspace Info
    show_full_cabbage = (w >= 80 and h >= 22)
    if show_full_cabbage:
        cabbage = render_bok_choy_logo()
        info_grid = Table.grid(expand=True)
        info_grid.add_column(justify="left", ratio=1)
        info_grid.add_column(justify="right")

        repo_name = Path.cwd().name
        branch_name = state.git_branch
        max_repo = 16 if w < 95 else 24
        if len(repo_name) > max_repo:
            repo_name = repo_name[: max_repo - 1] + "…"
        max_branch = 12 if w < 95 else 20
        if len(branch_name) > max_branch:
            branch_name = branch_name[: max_branch - 1] + "…"

        if w >= 95:
            plan_line = (
                f"[{THEME['architect']}]◆ plan [/] [{THEME['text']}]{state.planner}[/] "
                f"[{THEME['dim']}]{state.planner_model} · {state.planner_effort}[/]"
            )
            build_line = (
                f"[{THEME['builder']}]◆ build[/] [{THEME['text']}]{state.builder}[/] "
                f"[{THEME['dim']}]{state.builder_model} · {state.builder_effort}[/]"
            )
        else:
            plan_line = (
                f"[{THEME['architect']}]◆ plan [/] [{THEME['text']}]{state.planner}[/] "
                f"[{THEME['dim']}]{state.planner_model}[/]"
            )
            build_line = (
                f"[{THEME['builder']}]◆ build[/] [{THEME['text']}]{state.builder}[/] "
                f"[{THEME['dim']}]{state.builder_model}[/]"
            )

        left_info = (
            f"[{THEME['dim']}]repo  [/][bold {THEME['text']}]{repo_name}[/bold {THEME['text']}] "
            f"[{THEME['dim']}]on[/] [{THEME['ok']}]{branch_name}[/{THEME['ok']}]\n"
            f"[{THEME['dim']}]chat  [/]{conv_display}\n"
            f"{plan_line}\n"
            f"{build_line}"
        )
        right_info = (
            f"[{THEME['dim']}]gate  [/]{_mode_badge(state.permission_mode)}\n"
            f"[{THEME['dim']}]agents[/] [{THEME['text']}]{state.planner} · {state.builder}[/]\n\n"
            f"[yellow]F2[/] [{THEME['dim']}]menu ·[/] [yellow]F3[/] [{THEME['dim']}]activity[/]"
        )
        info_grid.add_row(Text.from_markup(left_info), Text.from_markup(right_info))

        meta_grid = Table.grid(padding=(0, 2 if w < 86 else 3))
        meta_grid.add_column(justify="left")
        meta_grid.add_column(justify="left", ratio=1)
        meta_grid.add_row(cabbage, info_grid)
        banner_items.append(meta_grid)
    elif w >= 65 and h >= 20:
        cabbage = render_bok_choy_logo()
        repo_name = Path.cwd().name
        branch_name = state.git_branch
        if len(repo_name) > 16:
            repo_name = repo_name[:15] + "…"
        if len(branch_name) > 12:
            branch_name = branch_name[:11] + "…"
        info_lines = [
            f"[{THEME['dim']}]repo [/][bold {THEME['text']}]{repo_name}[/] [{THEME['dim']}]on[/] [{THEME['ok']}]{branch_name}[/]",
            f"[{THEME['dim']}]chat [/]{conv_display}",
            f"[{THEME['architect']}]plan [/] [{THEME['text']}]{state.planner}[/] [{THEME['dim']}]{state.planner_model}[/]",
            f"[{THEME['builder']}]build[/] [{THEME['text']}]{state.builder}[/] [{THEME['dim']}]{state.builder_model}[/]",
            f"[{THEME['dim']}]gate  [/]{_mode_badge(state.permission_mode)}",
            f"[{THEME['dim']}]agents[/] [{THEME['text']}]{state.planner} · {state.builder}[/]",
            "",
            f"[yellow]F2[/] [{THEME['dim']}]menu ·[/] [yellow]F3[/] [{THEME['dim']}]activity[/]",
        ]
        meta_grid = Table.grid(padding=(0, 2))
        meta_grid.add_column(justify="left")
        meta_grid.add_column(justify="left", ratio=1)
        meta_grid.add_row(cabbage, Text.from_markup("\n".join(info_lines)))
        banner_items.append(meta_grid)
    else:
        compact_info = (
            f"[{THEME['dim']}]repo: [/][bold {THEME['text']}]{Path.cwd().name}[/] [{THEME['dim']}]({state.git_branch})[/]  "
            f"[{THEME['dim']}]chat: [/]{conv_display}\n"
            f"[{THEME['architect']}]plan: [/][{THEME['text']}]{state.planner}[/]  "
            f"[{THEME['builder']}]build: [/][{THEME['text']}]{state.builder}[/]  "
            f"[{THEME['dim']}]gate: [/]{_mode_badge(state.permission_mode)}\n"
            f"[yellow]F2[/] [{THEME['dim']}]menu ·[/] [yellow]F3[/] [{THEME['dim']}]activity[/]"
        )
        banner_items.append(Text.from_markup(compact_info))

    if w >= 75 and h >= 32:
        scan_table = build_agent_scan_table(state)
        if scan_table is not None:
            banner_items.extend([Rule(style=THEME["dim"]), scan_table])

    pad_h = 2 if w >= 86 else 1
    pad_v = 1 if (w >= 80 and h >= 26) else 0

    console.print(
        Panel(
            Group(*banner_items),
            box=box.ROUNDED,
            border_style=THEME["primary"],
            padding=(pad_v, pad_h),
            title=f"[{THEME['dim']}]◆ speiidev workspace ◆[/{THEME['dim']}]",
            title_align="left",
        )
    )

    if w >= 60:
        console.print(
            f"  [{THEME['dim']}]Type a task, or use[/] "
            f"[{THEME['primary']}]/agents[/] [{THEME['dim']}]·[/] "
            f"[{THEME['primary']}]/model[/] [{THEME['dim']}]·[/] [{THEME['primary']}]/effort[/] "
            f"[{THEME['dim']}]·[/] [{THEME['primary']}]/perms[/] [{THEME['dim']}]·[/] "
            f"[{THEME['primary']}]/help[/{THEME['primary']}]\n"
        )
    else:
        console.print(
            f"  [{THEME['dim']}]Type a task, or[/] [{THEME['primary']}]/help[/{THEME['primary']}]\n"
        )


_STREAM_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_STREAM_PHRASES = (
    "Booting agent runtime",
    "Reading workspace context",
    "Reasoning about the task",
    "Planning the next step",
    "Writing files",
    "Running tools",
    "Reviewing output",
)


def _stream_bar(elapsed: float, width: int = 22) -> str:
    """Indeterminate scrolling bar so the terminal never looks frozen."""
    pos = int(elapsed * 7) % (width + 4)
    cells = []
    for i in range(width):
        d = abs(i - pos)
        cells.append("█" if d == 0 else "▓" if d == 1 else "▒" if d == 2 else "░")
    return "".join(cells)


class _AgentStreamView:
    """Self-animating Rich renderable for a running agent subprocess.

    Rich's Live auto-refresh re-invokes ``__rich_console__`` on every frame, so
    the spinner, status phrase, scrolling bar and blinking cursor animate without
    any manual ``live.update`` calls (which keeps it smooth and cheap).
    """

    def __init__(self, cmd, title, border_color, badge, attempt, state, lines, activity):
        self.cmd = cmd
        self.cmd_preview = _preview_cmd(cmd) if cmd else ""
        self.title = title
        self.border_color = border_color
        self.badge = badge
        self.attempt = attempt
        self.state = state
        self.lines = lines
        self.activity = activity
        self.start_time = time.monotonic()
        self.done = False
        self.exit_code = 0

    def __rich_console__(self, console, options):
        yield self._panel(time.monotonic() - self.start_time, console, options)

    def _panel(self, elapsed: float, console: Console, options=None) -> Panel:
        color = self.border_color
        frame = _STREAM_SPINNER[int(elapsed * 12) % len(_STREAM_SPINNER)]
        blink = "▋" if int(elapsed * 2) % 2 == 0 else " "

        w = (options.max_width if options else None) or console.width or 80
        h = console.size.height or 24
        pad_h = 2 if w >= 80 else 1
        inner_w = max(16, w - (pad_h * 2 + 4))

        if not self.done:
            phrase = _STREAM_PHRASES[int(elapsed / 1.6) % len(_STREAM_PHRASES)]
            if w >= 70:
                header = Table.grid(expand=True)
                header.add_column(ratio=1)
                header.add_column(justify="right")
                header.add_row(
                    Text.from_markup(
                        f"[bold {color}]{frame} {self.badge}[/bold {color}] "
                        f"{self.title} (Attempt {self.attempt})"
                    ),
                    Text.from_markup(f"[dim]{elapsed:.1f}s[/dim]"),
                )
            else:
                short_title = self.title if len(self.title) <= 22 else self.title[:21] + "…"
                header = Text.from_markup(
                    f"[bold {color}]{frame} {self.badge}[/bold {color}] {short_title} [dim]{elapsed:.0f}s[/dim]"
                )
        else:
            icon = "✅" if self.exit_code == 0 else "❌"
            if w >= 60:
                header = Text.from_markup(
                    f"{icon} [bold {color}]{self.badge}[/bold {color}] {self.title} "
                    f"[dim](completed in {elapsed:.1f}s)[/dim]"
                )
            else:
                header = Text.from_markup(
                    f"{icon} [bold {color}]{self.badge}[/bold {color}] [dim]{elapsed:.0f}s[/dim]"
                )

        # Single-line command preview truncated with ellipsis
        cmd_shown = self.cmd_preview
        if len(cmd_shown) > inner_w - 4:
            cmd_shown = cmd_shown[: max(1, inner_w - 5)] + "…"
        proc_line = Text(f"$ {cmd_shown}", style=THEME["dim"], no_wrap=True)

        # Clamping lines vertically to prevent terminal overflow and Live scroll desync
        overhead = 8 if (self.activity and h >= 16) else 7
        max_body_lines = max(2, min(14, h - overhead - 2))

        if self.lines:
            visible = list(self.lines)[-max_body_lines:]
            body = Text()
            for idx, raw_line in enumerate(visible):
                clean = _strip_ansi(raw_line)
                if len(clean) > inner_w:
                    clean = clean[: max(1, inner_w - 1)] + "…"
                body.append(Text.from_ansi(clean))
                if idx < len(visible) - 1:
                    body.append("\n")
            if not self.done:
                body.append(f" {blink}", style=color)
        elif self.done:
            body = Text.from_markup(f"[{THEME['dim']}]No output.[/]")
        else:
            bar_len = max(8, min(22, inner_w - 32))
            bar = _stream_bar(elapsed, width=bar_len)
            if w >= 65:
                body = Text.from_markup(
                    f"[{color}]{frame}[/] [{THEME['text']}]{phrase}[/]…  "
                    f"[{THEME['dim']}]{bar}[/] {blink}"
                )
            else:
                body = Text.from_markup(
                    f"[{color}]{frame}[/] [{THEME['text']}]{phrase}[/]… {blink}"
                )

        rows: list = [header, Rule(style="dim"), proc_line, Rule(style="dim"), body]

        if self.activity and h >= 16:
            if not self.done:
                rows.append(
                    Text.from_markup(
                        f"[{THEME['dim']}]● {len(self.activity)} file(s) touched[/]"
                    )
                )
            if w >= 60 and h >= 18:
                rows.append(
                    Text.from_markup(f"[{THEME['dim']}]full activity → /log[/] ")
                )

        border = color if (not self.done or self.exit_code == 0) else "red"
        return Panel(
            Group(*rows),
            box=box.ROUNDED,
            border_style=border,
            padding=(0, pad_h),
        )


def stream_agent_box(
    cmd: list[str],
    title: str,
    border_color: str,
    badge: str,
    timeout: int,
    max_retries: int = 3,
    state: AgentState | None = None,
    label: str = "",
) -> int:
    all_lines: list[str] = []
    activity: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def ingest(clean: str) -> None:
        all_lines.append(clean)
        act = _parse_action(clean)
        if act:
            target = _action_target(act[0], act[1])
            if target is not None and (act[0], target) not in seen:
                seen.add((act[0], target))
                activity.append((act[0], target))

    def finalize() -> None:
        if state is None:
            return
        state.last_log = list(all_lines)
        state.last_files = list(activity)
        state.last_agent = label or badge
        state.last_log_path = _write_run_log(label or badge, all_lines)

    for attempt in range(1, max_retries + 1):
        lines: deque[str] = deque(maxlen=18)

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        is_windows = platform.system() == "Windows"
        safe_bin = get_safe_executable(cmd[0]) if cmd else None
        exec_cmd = [safe_bin] + list(cmd[1:]) if safe_bin else list(cmd)

        proc = subprocess.Popen(
            exec_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            shell=is_windows,
        )

        try:
            view = _AgentStreamView(
                cmd=exec_cmd,
                title=title,
                border_color=border_color,
                badge=badge,
                attempt=attempt,
                state=state,
                lines=lines,
                activity=activity,
            )
            with Live(view, console=console, refresh_per_second=20) as live:
                assert proc.stdout is not None
                for raw_line in proc.stdout:
                    clean = raw_line.rstrip("\r\n")
                    if clean:
                        ingest(clean)
                        lines.append(_fmt_activity(clean))
                    # Auto-refresh via Live thread is enough; optional tiny refresh
                    live.refresh()
                proc.wait(timeout=timeout)
                view.done = True
                view.exit_code = proc.returncode or 0
                live.refresh()
                finalize()

                if proc.returncode == 0:
                    return 0

                if attempt < max_retries:
                    console.print(f"[yellow]⚠️ Stream disconnected / exit {proc.returncode}. Retrying ({attempt}/{max_retries}) in 3s...[/yellow]")
                    time.sleep(3)
                    continue
                return proc.returncode

        except subprocess.TimeoutExpired:
            proc.kill()
            finalize()
            console.print(f"[bold red]⏱️ Agent timed out after {timeout}s[/bold red]")
            if attempt == max_retries:
                return 1
        except KeyboardInterrupt:
            proc.terminate()
            finalize()
            console.print("\n[bold yellow]⚡ Interrupted active agent step.[/bold yellow]")
            return 130

    return 1


def show_plan_card(plan_file: Path) -> None:
    if not plan_file.is_file():
        console.print(f"[yellow]No {plan_file} found in current directory.[/yellow]")
        return
    content = plan_file.read_text(encoding="utf-8")
    pad_h = 2 if console.width >= 80 else 1
    card_title = (
        f"[bold yellow]📋 {plan_file.name} (Shared Agent Spec)[/bold yellow]"
        if console.width >= 60
        else f"[bold yellow]📋 {plan_file.name}[/]"
    )
    console.print(
        Panel(
            Markdown(content),
            title=card_title,
            border_style="yellow",
            box=box.ROUNDED,
            padding=(1, pad_h),
        )
    )


# ============================================================================
# AGENT STEPS
# ============================================================================

def step_plan(state: AgentState, task: str) -> bool:
    profile = state.profile("plan")
    state.last_task = task
    persist_active_chat(state)
    prompt = (
        f"Create a phased implementation plan in {state.plan_file} for: {task}.\n"
        "Requirements:\n"
        "1. Do NOT modify any application source code files.\n"
        f"2. Write the plan to {state.plan_file} with exact file paths, interface "
        "signatures, and sequential '[ ]' checkboxes.\n"
        "3. Include exact test/verification commands for each phase."
    )
    cmd = profile.build(
        "plan", prompt, state.planner_model, state.planner_effort,
        True, state.plan_file, state.conversation_id,
    )
    state.last_status = "PLANNING"
    if not request_permission(
        state, f"{profile.key}:plan",
        f"Run {profile.label} architect (plan)", _preview_cmd(cmd),
    ):
        state.last_status = "PLAN_DENIED ⛔"
        return False

    rc = stream_agent_box(
        cmd=cmd,
        title=f"Designing architecture & writing {state.plan_file}",
        border_color=THEME["architect"],
        badge=f"[AGENT 1 · ARCHITECT · {profile.label.upper()}]",
        timeout=state.timeout_seconds,
        state=state,
        label="plan",
    )
    if rc != 0 or not state.plan_file.is_file():
        state.last_status = "PLAN_FAILED"
        return False

    show_plan_card(state.plan_file)
    state.last_status = "PLANNED"
    return True


def step_build(state: AgentState, is_fix_pass: bool = False) -> bool:
    profile = state.profile("build")
    before_snapshot = take_workspace_snapshot(exclude={state.plan_file})

    if is_fix_pass:
        title = "Applying fixes from the audit report"
        prompt = (
            f"Read the '## Fixes Required' section in {state.plan_file}. "
            "Fix every listed issue in the codebase, re-run the project tests, "
            f"update the build report in {state.plan_file}, and clear resolved items."
        )
    else:
        title = f"Implementing unchecked [ ] phases from {state.plan_file}"
        prompt = (
            f"Read {state.plan_file} and AGENTS.md (if present). "
            "Implement all unchecked '[ ]' tasks step-by-step. "
            "Run the verification/test commands, mark completed tasks as '[x]' "
            f"in {state.plan_file}, and append a concise '## Build Report' "
            f"at the bottom of {state.plan_file} listing modified files and test output."
        )

    cmd = profile.build(
        "build", prompt, state.builder_model, state.builder_effort,
        True, state.plan_file, None,
    )
    state.last_status = "BUILDING"
    phase = "fix" if is_fix_pass else "build"
    if not request_permission(
        state, f"{profile.key}:build",
        f"Run {profile.label} builder ({phase})", _preview_cmd(cmd),
    ):
        state.last_status = "BUILD_DENIED ⛔"
        return False

    rc = stream_agent_box(
        cmd=cmd,
        title=title,
        border_color=THEME["builder"],
        badge=f"[AGENT 2 · BUILDER · {profile.label.upper()}]",
        timeout=state.timeout_seconds,
        state=state,
        label="fix" if is_fix_pass else "build",
    )

    changes = compute_workspace_changes(before_snapshot, exclude={state.plan_file})
    review_and_approve_changes(
        changes, auto_approve=state.auto_approve or state.permission_mode == "auto"
    )

    if rc != 0 and not changes:
        state.last_status = "BUILD_FAILED ⛔"
    elif rc != 0:
        state.last_status = "BUILD_PARTIAL ⚠️"
    else:
        state.last_status = "BUILT ✅"
    return rc == 0


def clear_previous_audit_status(plan_file: Path) -> None:
    if not plan_file.is_file():
        return
    content = plan_file.read_text(encoding="utf-8")
    cleaned = (
        content.replace(VERIFIED_MARKER, "STATUS: PENDING_REAUDIT")
        .replace(FIXES_MARKER, "STATUS: PENDING_REAUDIT")
    )
    plan_file.write_text(cleaned, encoding="utf-8")


def step_audit(state: AgentState, attempt: int = 1) -> bool:
    profile = state.profile("plan")
    clear_previous_audit_status(state.plan_file)
    prompt = (
        f"Audit the builder's implementation against {state.plan_file}:\n"
        f"1. Read {state.plan_file} and run 'git status' and 'git diff' to inspect "
        "all code changes.\n"
        "2. Run the project's test/typecheck commands yourself to verify they pass.\n"
        f"3. Do NOT edit application code. Update ONLY {state.plan_file}:\n"
        f"   - If all tasks are complete and tests pass, append '{VERIFIED_MARKER}' "
        f"at the very bottom of {state.plan_file}.\n"
        f"   - If any bugs, missing requirements, or test failures exist, append "
        f"'{FIXES_MARKER}' and list the exact actionable fixes under a "
        f"'## Fixes Required' heading at the bottom of {state.plan_file}."
    )
    cmd = profile.build(
        "plan", prompt, state.planner_model, state.planner_effort,
        True, state.plan_file, state.conversation_id,
    )
    state.last_status = f"AUDITING ({attempt}/{state.max_retries})"
    if not request_permission(
        state, f"{profile.key}:audit",
        f"Run {profile.label} auditor (audit)", _preview_cmd(cmd),
    ):
        state.last_status = "AUDIT_DENIED ⛔"
        return False

    stream_agent_box(
        cmd=cmd,
        title=f"Auditing git diff, test suite & {state.plan_file} (Attempt {attempt}/{state.max_retries})",
        border_color=THEME["auditor"],
        badge=f"[AGENT 1 · AUDITOR · {profile.label.upper()}]",
        timeout=state.timeout_seconds,
        state=state,
        label="audit",
    )

    if not state.plan_file.is_file():
        return False
    plan_text = state.plan_file.read_text(encoding="utf-8")
    verified = VERIFIED_MARKER in plan_text and FIXES_MARKER not in plan_text
    state.last_status = "VERIFIED ✅" if verified else "NEEDS_FIXES ⚠️"
    return verified


def show_git_diff_colored() -> None:
    git_bin = get_safe_executable("git") or "git"
    res = subprocess.run(
        [git_bin, "diff"],
        capture_output=True,
        text=True,
        shell=platform.system() == "Windows",
    )
    if not res.stdout.strip():
        console.print("[dim]No uncommitted git diff found.[/dim]")
        return
    syntax = Syntax(res.stdout, "diff", theme="monokai", line_numbers=True)
    console.print(
        Panel(
            syntax,
            title="[bold green]Git Diff (+ New Code / - Old Code)[/bold green]",
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _fetch_models(profile: AgentProfile) -> list[tuple[str, str]]:
    if not profile.models_cmd:
        return []
    try:
        cmd = list(profile.models_cmd)
        safe_bin = get_safe_executable(cmd[0])
        if safe_bin:
            cmd[0] = safe_bin
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=25,
            shell=platform.system() == "Windows",
        )
        pairs: list[tuple[str, str]] = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("fetching"):
                continue
            parts = line.split("\t")
            mid = parts[0].strip()
            name = parts[1].strip() if len(parts) > 1 else mid
            if mid:
                pairs.append((mid, name))
        return pairs
    except Exception:
        return []


def _choose_model(
    title: str, options: list[tuple[str, str]], current: str | None = None
) -> str | None:
    menu_options = [
        (mid, name if name and name != mid else mid) for mid, name in options
    ]
    menu_options.append(("__custom__", "✎  Type a custom model id…"))
    picked = searchable_select(title, menu_options, current=current)
    if picked is None:
        return None
    if picked == "__custom__":
        raw = Prompt.ask(
            f"  [{THEME['primary']}]Custom model id[/] [{THEME['dim']}](blank to cancel)[/]",
            default="",
        ).strip()
        return raw or None
    return picked


def handle_model_switcher(state: AgentState) -> None:
    """View or change the model used by the planner and builder agents."""
    table = Table(
        title="Current Model Configuration",
        box=box.ROUNDED,
        border_style=THEME["primary"],
    )
    table.add_column("Role", style=f"bold {THEME['primary']}")
    table.add_column("Agent", style=THEME["dim"])
    table.add_column("Active model", style=f"bold {THEME['text']}")
    table.add_row("Planner / Auditor", state.planner, state.planner_model)
    table.add_row("Builder", state.builder, state.builder_model)
    console.print(table)

    role = arrow_menu(
        "Which model?",
        [
            ("plan", f"Planner / Auditor  ({state.planner})"),
            ("build", f"Builder  ({state.builder})"),
        ],
        default="plan",
    )
    if role not in ("plan", "build"):
        return

    profile = state.profile(role)
    attr = "planner_model" if role == "plan" else "builder_model"
    current = getattr(state, attr)
    if profile.models_cmd:
        with console.status(f"[{THEME['dim']}]Fetching {profile.label} models…[/]"):
            options = _fetch_models(profile)
    else:
        options = []
    picked = _choose_model(
        f"Available {profile.label} models", options, current=current
    )
    if picked:
        setattr(state, attr, picked)
        console.print(f"[{THEME['ok']}]✓ {role} model → {picked}[/]\n")
    else:
        console.print(f"[{THEME['dim']}]Unchanged ({current}).[/]\n")


def handle_effort_switcher(state: AgentState) -> None:
    """Increase/decrease the reasoning intensity of each agent."""
    planner_prof = state.profile("plan")
    builder_prof = state.profile("build")
    table = Table(
        title="Reasoning Effort (model intensity)",
        box=box.ROUNDED,
        border_style=THEME["accent"],
    )
    table.add_column("Role", style=f"bold {THEME['accent']}")
    table.add_column("Agent", style=THEME["dim"])
    table.add_column("Current", style=f"bold {THEME['text']}")
    table.add_column("Options", style=THEME["dim"])
    table.add_row(
        "Planner", planner_prof.label, state.planner_effort,
        ", ".join(planner_prof.efforts),
    )
    table.add_row(
        "Builder", builder_prof.label, state.builder_effort,
        ", ".join(builder_prof.efforts),
    )
    console.print(table)

    if state.planner == "agy" and state.planner_model not in ("", "default"):
        console.print(
            f"  [{THEME['warn']}]agy effort may be ignored — model "
            f"'{state.planner_model}' already encodes effort[/]"
        )
    role = arrow_menu(
        "Set reasoning effort",
        [
            ("plan", f"Planner effort  ({state.planner})"),
            ("build", f"Builder effort  ({state.builder})"),
        ],
        default="plan",
    )
    if role not in ("plan", "build"):
        return

    profile = state.profile(role)
    attr = "planner_effort" if role == "plan" else "builder_effort"
    val = arrow_menu(
        f"{role.capitalize()} effort — {profile.label}",
        [(e, e) for e in profile.efforts],
        default=getattr(state, attr),
    )
    if val is None:
        return
    setattr(state, attr, val)
    console.print(f"[{THEME['ok']}]✓ {role} effort → {val}[/]\n")


def handle_permissions(state: AgentState) -> None:
    """Show and change the command permission gate mode."""
    table = Table(
        title="Command Permission Gate",
        box=box.ROUNDED,
        border_style=THEME["auditor"],
    )
    table.add_column("Mode", style=f"bold {THEME['text']}")
    table.add_column("Behaviour", style=THEME["dim"])
    table.add_row("ask", "Prompt allow / deny / allow-always before each agent command")
    table.add_row("auto", "Never prompt — approve everything")
    table.add_row("deny", "Block all agent commands")
    console.print(table)
    console.print(f"  Active mode: {_mode_badge(state.permission_mode)}")
    if state.approved_actions:
        console.print(
            f"  [{THEME['dim']}]Remembered (allow-always):[/] "
            f"[{THEME['ok']}]{', '.join(sorted(state.approved_actions))}[/]"
        )

    choice = arrow_menu(
        "Permission gate mode",
        [
            ("ask", "ask   — prompt before each agent command"),
            ("auto", "auto  — approve everything"),
            ("deny", "deny  — block everything"),
            ("reset", "reset — clear remembered approvals"),
        ],
        default=state.permission_mode,
    )
    if choice == "reset":
        state.approved_actions.clear()
        console.print(f"[{THEME['ok']}]✓ cleared remembered approvals[/]\n")
    elif choice:
        state.permission_mode = choice
        console.print(f"[{THEME['ok']}]✓ permission mode → {choice}[/]\n")


def _ask_role(state: AgentState, role: str, first_run: bool = False) -> None:
    """Prompt the user to pick an installed agent CLI for a role."""
    attr = "planner" if role == "plan" else "builder"
    model_attr = "planner_model" if role == "plan" else "builder_model"
    effort_attr = "planner_effort" if role == "plan" else "builder_effort"
    current = getattr(state, attr)
    candidates = installed_profiles()
    role_label = "Planner / Auditor" if role == "plan" else "Builder"

    table = Table(
        title=f"{role_label} agent",
        box=box.ROUNDED,
        border_style=THEME["architect"] if role == "plan" else THEME["builder"],
    )
    table.add_column("Agent", style=f"bold {THEME['accent']}")
    table.add_column("Status", justify="center")
    table.add_column("About", style=THEME["dim"])
    for key, prof in PROFILES.items():
        can = key in candidates
        exists = get_safe_executable(prof.binary) is not None
        if can and exists:
            status = f"[{THEME['ok']}]✓ ready[/]"
        elif can:
            status = f"[{THEME['dim']}]not installed[/]"
        else:
            status = f"[{THEME['dim']}]n/a[/]"
        name = f"{key}" + (
            f" [{THEME['primary']}](current)[/]" if key == current else ""
        )
        table.add_row(name, status, prof.blurb)
    console.print(table)

    if not candidates:
        console.print(
            f"[{THEME['err']}]✗ No installed agent can serve as the {role_label}.[/]"
        )
        return

    default = current if current in candidates else candidates[0]
    pick = arrow_menu(
        f"Choose {role_label} agent",
        [(k, f"{k}  —  {PROFILES[k].blurb}") for k in candidates],
        default=default,
    )
    if pick is None:
        pick = current
    if pick != current:
        setattr(state, attr, pick)
        setattr(state, model_attr, "default")
        setattr(state, effort_attr, "default")
    console.print(f"[{THEME['ok']}]✓ {role_label} → {pick}[/]\n")


def build_agent_scan_table(state: AgentState) -> Table | None:
    """Build a table of agent CLIs installed on this PC + current selection."""
    found = installed_profiles()
    if not found:
        return None

    table = Table(
        title="🔎 Installed agents on this PC",
        box=box.ROUNDED,
        border_style=THEME["primary"],
        title_style=f"bold {THEME['primary']}",
        padding=(0, 1),
    )
    table.add_column("Agent", style=f"bold {THEME['accent']}", no_wrap=True)
    table.add_column("Plan / Audit", justify="center")
    table.add_column("Build", justify="center")
    table.add_column("Selected for", style=THEME["text"])
    for key in found:
        prof = PROFILES[key]
        roles = []
        if key == state.planner:
            roles.append(f"[{THEME['architect']}]planner[/]")
        if key == state.builder:
            roles.append(f"[{THEME['builder']}]builder[/]")
        table.add_row(
            key,
            f"[{THEME['ok']}]◆[/]" if "plan" in prof.roles else f"[{THEME['dim']}]—[/]",
            f"[{THEME['ok']}]◆[/]" if "build" in prof.roles else f"[{THEME['dim']}]—[/]",
            " · ".join(roles) if roles else f"[{THEME['dim']}]—[/]",
        )
    return table


def run_setup_wizard(state: AgentState, first_run: bool = False) -> None:
    """Scan the system for agent CLIs and assign one to each role."""
    heading = "First-run setup" if first_run else "Agent setup"
    found = installed_profiles()
    if found:
        found_line = (
            f"[{THEME['ok']}]Found {len(found)} agent CLI(s):[/] "
            + ", ".join(f"[bold {THEME['text']}]{k}[/]" for k in found)
        )
    else:
        found_line = f"[{THEME['err']}]No supported agent CLIs found on your PATH.[/]"
    console.print(
        Panel(
            f"[bold {THEME['primary']}]{heading}[/]\n"
            f"[{THEME['dim']}]Scanning your PATH for installed agent CLIs…[/]\n"
            f"{found_line}\n"
            f"[{THEME['text']}]Choose which agent CLI plays each role.[/] "
            f"[{THEME['dim']}]Change this anytime with[/] "
            f"[{THEME['primary']}]/agents[/][{THEME['dim']}].[/]",
            box=box.ROUNDED,
            border_style=THEME["primary"],
            padding=(1, 2),
        )
    )
    _ask_role(state, "plan", first_run)
    _ask_role(state, "build", first_run)

    planner = state.profile("plan")
    builder = state.profile("build")
    console.print(
        f"  [{THEME['architect']}]◆ planner[/] [{THEME['text']}]{planner.label}[/]"
        f"   [{THEME['builder']}]builder ◆[/] [{THEME['text']}]{builder.label}[/]\n"
    )


def _report_build_failure(state: AgentState, fix_pass: bool = False) -> None:
    profile = state.profile("build")
    kind = "fix pass" if fix_pass else "build"
    console.print(
        Panel(
            f"[bold {THEME['err']}]❌ Builder disconnected during the {kind}.[/]\n"
            f"[{THEME['dim']}]The {profile.label} agent exited with an error and "
            f"made no changes, so there is nothing new to audit. Stopping the "
            f"pipeline instead of re-planning.[/]\n\n"
            f"[{THEME['text']}]Next steps:[/]  "
            f"[{THEME['primary']}]/build[/] to retry  ·  "
            f"[{THEME['primary']}]/agents[/] to switch builder  ·  "
            f"[{THEME['primary']}]/perms[/] to check the gate",
            border_style=THEME["err"],
            box=box.ROUNDED,
        )
    )


def run_full_pipeline(state: AgentState, task: str) -> int:
    if not step_plan(state, task):
        return 1

    if console.is_terminal:
        choice = arrow_menu(
            "📋 Plan ready — review before building",
            [
                ("y", "▶  Proceed to build"),
                ("n", "⏸  Pause — I'll review / edit the plan first"),
            ],
            text=f"{state.plan_file} is ready. Approve before the builder runs.",
            default="y",
        )
    else:
        choice = "y" if state.permission_mode == "auto" else None

    if choice != "y":
        console.print(
            f"[{THEME['warn']}]Paused. Edit {state.plan_file} and press /build or use the menu when ready.[/]\n"
        )
        return 0

    if not step_build(state, is_fix_pass=False):
        if state.last_status.startswith("BUILD_DENIED"):
            console.print(
                f"[{THEME['warn']}]Build was denied — nothing changed. Resume with "
                f"[{THEME['primary']}]/build[/] when ready.[/]\n"
            )
            return 0
        if state.last_status.startswith("BUILD_FAILED"):
            _report_build_failure(state)
            return 1

    for attempt in range(1, state.max_retries + 1):
        if step_audit(state, attempt=attempt):
            console.print(
                Panel(
                    f"[bold {THEME['ok']}]✅ VERIFIED![/] {state.profile('plan').label} "
                    f"confirmed all tasks in [bold]{state.plan_file}[/bold] passed "
                    f"implementation and testing.",
                    border_style=THEME["ok"],
                    box=box.ROUNDED,
                )
            )
            return 0

        if state.last_status.startswith("AUDIT_DENIED"):
            console.print(
                f"[{THEME['warn']}]Audit was denied — stopping the pipeline.[/]\n"
            )
            return 0

        show_plan_card(state.plan_file)
        if attempt < state.max_retries:
            console.print(
                f"[bold {THEME['warn']}]🔄 Auto-Fix Loop ({attempt}/{state.max_retries}): "
                f"Sending {state.profile('build').label} back to fix audit issues…[/]\n"
            )
            if not step_build(state, is_fix_pass=True):
                if state.last_status.startswith("BUILD_DENIED"):
                    console.print(
                        f"[{THEME['warn']}]Fix pass denied — stopping the pipeline.[/]\n"
                    )
                    return 0
                if state.last_status.startswith("BUILD_FAILED"):
                    _report_build_failure(state, fix_pass=True)
                    return 1

    console.print(
        Panel(
            f"[bold {THEME['err']}]❌ Max retries ({state.max_retries}) reached.[/] "
            f"Inspect [bold]{state.plan_file}[/bold] or run "
            f"[{THEME['primary']}]/build[/] to continue.",
            border_style=THEME["err"],
            box=box.ROUNDED,
        )
    )
    return 1


def show_background_log(state: AgentState, mode: str = "files") -> None:
    """Show what the last agent did in the background (files, full log, path)."""
    if not state.last_log:
        console.print(
            f"[{THEME['dim']}]No background activity captured yet — run a task first.[/]\n"
        )
        return

    mode = (mode or "files").lower()
    agent = state.last_agent or "agent"

    if mode in ("raw", "all", "full", "text"):
        console.print(
            Panel(
                Text.from_ansi("\n".join(state.last_log)),
                title=f"[bold {THEME['primary']}]🧾 Background log · {agent}[/]",
                subtitle=f"[{THEME['dim']}]{state.last_log_path or 'in-memory only'}[/]",
                border_style=THEME["primary"],
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )
        return

    if mode in ("path", "file", "where"):
        console.print(
            f"[{THEME['ok']}]Log file:[/] {state.last_log_path or '(not written)'}\n"
        )
        return

    files = state.last_files or parse_background_activity(state.last_log)
    if not files:
        console.print(
            f"[{THEME['dim']}]No file operations detected in the last run.[/] "
            f"[{THEME['primary']}]/log raw[/][{THEME['dim']}] for the full transcript.[/]\n"
        )
        return

    table = Table(
        title=f"📂 Files touched · {agent}",
        box=box.ROUNDED,
        border_style=THEME["builder"],
    )
    table.add_column("Action", style=f"bold {THEME['accent']}", no_wrap=True)
    table.add_column("File (full path)", style=THEME["text"])
    for action, target in files:
        color = (
            THEME["ok"]
            if action in ("Read", "Glob", "Grep", "List", "Search", "Find")
            else THEME["warn"]
        )
        table.add_row(f"[{color}]● {action}[/]", f"[{THEME['text']}]{target}[/]")
    console.print(table)


def open_activity_viewer(state: AgentState) -> None:
    """Clickable background-activity viewer (arrow keys, no commands)."""
    while True:
        mode = arrow_menu(
            "Background activity",
            [
                ("files", "📂  Files touched  (full paths)"),
                ("raw", "🧾  Full transcript"),
                ("path", "🗺   Log file location"),
                ("back", "↩  Back"),
            ],
            text=(state.last_agent or "no run yet"),
            default="files",
        )
        if mode in (None, "back"):
            return
        show_background_log(state, mode)


def open_action_menu(state: AgentState) -> None:
    """Main clickable action menu (arrow keys + Enter)."""
    action = arrow_menu(
        "⌘  Quick actions",
        [
            ("activity", "📂  Background activity  (what the agent did)"),
            ("plan", "📋  Show PLAN.md"),
            ("diff", "🔀  Show git diff"),
            ("agents", "🤖  Switch agents"),
            ("model", "🧠  Switch model"),
            ("effort", "⚡  Change effort"),
            ("perms", "🔐  Permission gate"),
            ("help", "❓  Help"),
            ("exit", "🚪  Exit"),
        ],
        text="↑/↓ move · Enter select · Esc close",
    )
    if action == "activity":
        open_activity_viewer(state)
    elif action == "plan":
        show_plan_card(state.plan_file)
    elif action == "diff":
        show_git_diff_colored()
    elif action == "agents":
        run_setup_wizard(state)
    elif action == "model":
        handle_model_switcher(state)
    elif action == "effort":
        handle_effort_switcher(state)
    elif action == "perms":
        handle_permissions(state)
    elif action == "help":
        show_help()


def show_help() -> None:
    table = Table(
        title="⌘ Slash Commands",
        box=box.ROUNDED,
        border_style=THEME["primary"],
        title_style=f"bold {THEME['primary']}",
        padding=(0, 1),
    )
    table.add_column("Command", style=f"bold {THEME['accent']}", no_wrap=True)
    table.add_column("Description", style=THEME["text"])

    table.add_row("F2", "⌘ Action menu — navigate with ↑/↓ and Enter (no typing)")
    table.add_row("F3", "📂 Background activity — files the agent touched, full paths")
    table.add_row("<any text>", "Full flow: Plan → [Enter] → Build → Diff Gate → Audit (retry loop)")
    table.add_row("", "")
    table.add_row("Menus", "Agents, model, effort, permissions & allow/deny are arrow-key menus")
    table.add_row("", "")
    table.add_row("/agents", "Assign which agent CLI plays the planner & builder roles")
    table.add_row("/model", "Switch the planner / builder model (live model discovery)")
    table.add_row("/effort", "Increase or decrease reasoning intensity per role")
    table.add_row("/perms", "Permission gate mode: ask · auto · deny, and clear allow-always memory")
    table.add_row("/log", "Background activity: files the agent touched (full paths)")
    table.add_row("", "")
    table.add_row("/plan <task>", "Run ONLY the planner — active model & effort")
    table.add_row("/build", "Run ONLY the builder + color-coded diff approval")
    table.add_row("/audit", "Run ONLY the planner to audit git diff & tests")
    table.add_row("/conv <id>", "Set/clear the conversation UUID (current chat only)")
    table.add_row("/rember [n|id]", "List remembered chats, or resume one by number/id")
    table.add_row("", "")
    table.add_row("/diff", "Show color-coded git diff (+ green new / - red old)")
    table.add_row("/show", "Render PLAN.md with formatted Markdown")
    table.add_row("/font <text>", "Render text in 3D wireframe shadow or mini block font")
    table.add_row("/clear", "Clear the screen and redraw the banner")
    table.add_row("Ctrl+L", "Clear the screen and redraw responsive banner")
    table.add_row("/exit", "Quit SpeiiDev")
    console.print(table)


def handle_rember(state: AgentState, arg: str = "") -> None:
    """List remembered chats or resume one by index/id."""
    entries = load_rember()
    arg = arg.strip()

    if not entries:
        console.print(
            f"[{THEME['warn']}]No remembered chats yet.[/] "
            f"Set one with [bold]{escape('/conv <id>')}[/bold] and it will be stored in "
            f"{REMBER_FILE.name}."
        )
        return

    if not arg:
        w = console.width
        table = Table(
            title="⌘ Remembered Chats",
            box=box.ROUNDED,
            border_style=THEME["primary"],
            title_style=f"bold {THEME['primary']}",
            padding=(0, 1),
        )
        table.add_column("#", style=f"bold {THEME['accent']}", justify="right", no_wrap=True)
        table.add_column("Chat ID", style=THEME["text"], no_wrap=True)
        if w >= 65:
            table.add_column("Time", style=THEME["dim"], no_wrap=True)
        task_max_w = max(15, min(40, w - 30))
        table.add_column("Task", style=THEME["text"], overflow="ellipsis", max_width=task_max_w)
        for i, entry in enumerate(entries, 1):
            label = str(entry.get("label", ""))
            if label.startswith("chat ") or label.startswith("agent"):
                label = ""
            row_items = [str(i), str(entry.get("id", ""))]
            if w >= 65:
                row_items.append(str(entry.get("time", "")))
            row_items.append(label)
            table.add_row(*row_items)
        console.print(table)
        console.print(
            f"[{THEME['dim']}]Resume with[/] "
            f"[bold {THEME['accent']}]{escape('/rember <#|id>')}[/]\n"
        )
        return

    selected: dict | None = None
    if arg.isdigit() and 1 <= int(arg) <= len(entries):
        selected = entries[int(arg) - 1]
    else:
        selected = next((e for e in entries if e.get("id") == arg), None)

    if selected is None:
        console.print(f"[{THEME['err']}]No remembered chat matches '{arg}'.[/]")
        return

    state.conversation_id = str(selected["id"])
    remember_conversation(state.conversation_id, selected.get("label", ""))
    console.print(
        f"[{THEME['ok']}]✓ Resumed chat {state.conversation_id}[/] "
        f"[{THEME['dim']}]({selected.get('time', '')})[/]"
    )


def interactive_repl(state: AgentState) -> int:
    console.clear()
    print_banner(state)

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    completer = WordCompleter(SLASH_COMMANDS, ignore_case=True, sentence=True)
    style = Style.from_dict(
        {
            "bottom-toolbar": "bg:#1e1e2e #cdd6f4",
            "prompt": "bold ansigreen",
        }
    )

    def bottom_toolbar() -> HTML:
        term_cols = shutil.get_terminal_size((80, 24)).columns
        conv_label = (
            state.conversation_id[:8] + "…"
            if state.conversation_id
            else state.session_id[:8] + "…"
        )
        gate = {"auto": "AUTO", "deny": "DENY", "ask": "ASK"}.get(
            state.permission_mode, "ASK"
        )
        if term_cols >= 95:
            return HTML(
                f" <b>⌘ SPEIIDEV</b> 🥬 "
                f"<ansicyan>{state.planner}</ansicyan> <b>{state.planner_model[:16]}</b> "
                f"<ansimagenta>{state.builder}</ansimagenta> <b>{state.builder_model[:16]}</b>  "
                f"gate <b>{gate}</b>  chat <b>{conv_label}</b>  "
                f"<ansigreen>{state.last_status}</ansigreen>  "
                f"<ansiyellow>F2 menu · F3 activity</ansiyellow> "
            )
        elif term_cols >= 75:
            return HTML(
                f" <b>⌘ SPEIIDEV</b> "
                f"<ansicyan>{state.planner}</ansicyan> "
                f"<ansimagenta>{state.builder}</ansimagenta>  "
                f"gate <b>{gate}</b>  chat <b>{conv_label}</b>  "
                f"<ansigreen>{state.last_status}</ansigreen>  "
                f"<ansiyellow>F2 menu</ansiyellow> "
            )
        elif term_cols >= 50:
            return HTML(
                f" <b>⌘</b> <ansicyan>{state.planner}</ansicyan>·<ansimagenta>{state.builder}</ansimagenta> "
                f"gate <b>{gate}</b> chat <b>{conv_label}</b> <ansiyellow>F2</ansiyellow> "
            )
        else:
            return HTML(
                f" <b>⌘</b> <b>{gate}</b> <ansiyellow>F2</ansiyellow> "
            )

    try:
        history = FileHistory(str(HISTORY_FILE))
    except OSError:
        history = FileHistory(str(Path.home() / ".speiidev_history"))

    MENU_SENTINEL = "\x00__menu__"
    ACTIVITY_SENTINEL = "\x00__activity__"

    kb = KeyBindings()

    @kb.add(Keys.F2)
    def _open_menu(event):
        event.app.exit(result=MENU_SENTINEL)

    @kb.add(Keys.F3)
    def _open_activity(event):
        event.app.exit(result=ACTIVITY_SENTINEL)

    @kb.add("c-l")
    def _clear_and_redraw(event):
        console.clear()
        print_banner(state)
        event.app.renderer.erase()

    session: PromptSession[str] = PromptSession(
        history=history,
        completer=completer,
        bottom_toolbar=bottom_toolbar,
        style=style,
        key_bindings=kb,
        refresh_interval=0.5,
    )

    orig_on_resize = session.app._on_resize
    resize_timer: list[asyncio.TimerHandle | None] = [None]

    def _do_redraw() -> None:
        if getattr(session.app, "is_running", False):
            console.clear()
            print_banner(state)
            try:
                session.app.renderer.erase(leave_alternate_screen=False)
                session.app._request_absolute_cursor_position()
                session.app._redraw()
            except Exception:
                orig_on_resize()

    def _handle_resize() -> None:
        try:
            loop = asyncio.get_running_loop()
            if resize_timer[0] is not None:
                resize_timer[0].cancel()
            resize_timer[0] = loop.call_later(0.08, _do_redraw)
        except Exception:
            _do_redraw()

    session.app._on_resize = _handle_resize

    while True:
        try:
            user_input = session.prompt([("class:prompt", "❯ ")]).strip()
        except (EOFError, KeyboardInterrupt):
            persist_active_chat(state)
            save_config(state)
            console.print("\n[dim]Goodbye![/dim]")
            return 0

        if user_input == MENU_SENTINEL:
            open_action_menu(state)
            save_config(state)
            continue
        if user_input == ACTIVITY_SENTINEL:
            open_activity_viewer(state)
            save_config(state)
            continue

        if not user_input:
            continue

        if user_input in ("/exit", "/quit", "exit", "quit"):
            persist_active_chat(state)
            save_config(state)
            console.print("[dim]Goodbye![/dim]")
            return 0
        elif user_input == "/help":
            show_help()
        elif user_input == "/clear":
            console.clear()
            print_banner(state)
        elif user_input == "/show":
            show_plan_card(state.plan_file)
        elif user_input == "/diff":
            show_git_diff_colored()
        elif user_input.startswith("/font"):
            txt = user_input[5:].strip()
            if not txt:
                console.print("[yellow]Usage: /font <text> (or /font --mini <text>)[/yellow]")
            else:
                style = "mini" if txt.startswith("--mini ") else "claude"
                if style == "mini":
                    txt = txt[7:].strip()
                console.print(f"\n[bold {THEME['primary']}]{render_block_text(txt, style=style, color='none')}[/]\n")
        elif user_input == "/agents":
            run_setup_wizard(state)
        elif user_input == "/model":
            handle_model_switcher(state)
        elif user_input == "/effort":
            handle_effort_switcher(state)
        elif user_input == "/perms":
            handle_permissions(state)
        elif user_input.startswith("/log"):
            parts = user_input.split(maxsplit=1)
            show_background_log(state, parts[1].strip() if len(parts) > 1 else "files")
        elif user_input == "/auto":
            state.permission_mode = (
                "ask" if state.permission_mode == "auto" else "auto"
            )
            state.auto_approve = state.permission_mode == "auto"
            console.print(
                f"[{THEME['primary']}]Permission gate:[/] "
                f"{_mode_badge(state.permission_mode)}\n"
            )
        elif user_input.startswith("/conv"):
            parts = user_input.split(maxsplit=1)
            if len(parts) > 1:
                state.conversation_id = parts[1].strip()
                remember_conversation(state.conversation_id)
                console.print(
                    f"[green]✓ Active conversation ID set to: {state.conversation_id}[/green]"
                )
            else:
                state.conversation_id = None
                console.print("[yellow]Conversation ID cleared (using new chat).[/yellow]")
        elif user_input.startswith("/rember"):
            parts = user_input.split(maxsplit=1)
            handle_rember(state, parts[1] if len(parts) > 1 else "")
        elif user_input.startswith("/plan"):
            task = user_input[5:].strip()
            if not task:
                console.print("[yellow]Usage: /plan <describe feature>[/yellow]")
            else:
                step_plan(state, task)
        elif user_input == "/build":
            step_build(state, is_fix_pass=False)
        elif user_input == "/audit":
            if step_audit(state, attempt=1):
                console.print(f"[bold {THEME['ok']}]✅ Audit Passed![/]\n")
            else:
                show_plan_card(state.plan_file)
        else:
            run_full_pipeline(state, user_input)

        save_config(state)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SpeiiDev: Interactive Multi-Agent TUI with Model Switcher & Conversation History"
    )
    parser.add_argument("task", nargs="*", help="Optional task to run immediately")
    parser.add_argument("--plan-file", type=Path, default=Path("PLAN.md"))
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--conversation", type=str, default=None, help="Antigravity conversation UUID")
    parser.add_argument("--planner", type=str, default=None, choices=list(PROFILES), help="Agent CLI for the planner/auditor role")
    parser.add_argument("--builder", type=str, default=None, choices=list(PROFILES), help="Agent CLI for the builder role")
    parser.add_argument("--planner-model", type=str, default=None, help="Model for the planner (default: saved)")
    parser.add_argument("--builder-model", type=str, default=None, help="Model for the builder (default: saved)")
    parser.add_argument("--planner-effort", type=str, default=None, help="Reasoning effort for the planner")
    parser.add_argument("--builder-effort", type=str, default=None, help="Reasoning effort for the builder")
    parser.add_argument("--permissions", type=str, default=None, choices=["ask", "auto", "deny"], help="Command permission gate mode")
    parser.add_argument("--no-splash", action="store_true", help="Skip the boot animation")
    parser.add_argument("--no-save", action="store_true", help="Do not persist session state to disk")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve all plans and diffs (alias for --permissions auto)")
    parser.add_argument("--font", type=str, default=None, help="Render text in block art font and exit")
    parser.add_argument(
        "--font-style",
        type=str,
        choices=["claude", "3d", "mini", "2line"],
        default="claude",
        help="Font style: claude (3D wireframe shadow) or mini (compact 2-line)",
    )
    args = parser.parse_args()

    if args.font is not None:
        console.print(f"[bold {THEME['primary']}]{render_block_text(args.font, style=args.font_style, color='none')}[/]")
        return 0

    cfg = load_config()
    first_run = not CONFIG_FILE.exists()

    permission_mode = (
        "auto" if args.yes else args.permissions or cfg.get("permission_mode", "ask")
    )
    if permission_mode not in ("ask", "auto", "deny"):
        permission_mode = "ask"

    planner = args.planner or cfg.get("planner") or first_installed_for("plan") or installed_profiles()[0] if installed_profiles() else "agy"
    builder = args.builder or cfg.get("builder") or first_installed_for("build") or installed_profiles()[0] if installed_profiles() else "opencode"
    if planner not in PROFILES or not get_safe_executable(PROFILES[planner].binary):
        candidates = installed_profiles()
        planner = candidates[0] if candidates else "agy"
    if builder not in PROFILES or not get_safe_executable(PROFILES[builder].binary):
        candidates = installed_profiles()
        builder = candidates[0] if candidates else "opencode"

    state = AgentState(
        plan_file=args.plan_file,
        max_retries=args.max_retries,
        auto_approve=permission_mode == "auto",
        conversation_id=args.conversation,
        planner=planner,
        builder=builder,
        planner_model=args.planner_model or cfg.get("planner_model", "default"),
        builder_model=args.builder_model or cfg.get("builder_model", "default"),
        planner_effort=args.planner_effort or cfg.get("planner_effort", "default"),
        builder_effort=args.builder_effort or cfg.get("builder_effort", "default"),
        permission_mode=permission_mode,
        persist=not args.no_save,
    )
    saved = cfg.get("approved_actions")
    if isinstance(saved, list):
        state.approved_actions = {str(a) for a in saved}

    if state.conversation_id:
        remember_conversation(state.conversation_id)

    if not args.no_splash:
        run_splash(state)

    explicit_agents = bool(args.planner or args.builder)
    interactive = console.is_terminal and not args.task

    planner_missing = get_safe_executable(PROFILES[state.planner].binary) is None
    builder_missing = get_safe_executable(PROFILES[state.builder].binary) is None
    needs_pick = first_run or planner_missing or builder_missing

    if interactive and not args.no_save:
        if needs_pick and not explicit_agents:
            run_setup_wizard(state, first_run=first_run)
            save_config(state)

    missing = [
        f"{role}:{key} ({PROFILES[key].binary})"
        for role, key in (("planner", state.planner), ("builder", state.builder))
        if get_safe_executable(PROFILES[key].binary) is None
    ]
    if missing:
        console.print(
            f"[bold red]❌ No agent CLI found for:[/bold red] {', '.join(missing)}\n"
            f"[{THEME['text']}]Install at least one supported agent on your PATH:[/] "
            f"{', '.join(PROFILES)}.\n"
            f"[{THEME['dim']}]Tip: run [/][{THEME['primary']}]/agents[/]"
            f"[{THEME['dim']}] inside the tool to scan and pick again.[/]"
        )
        return 1

    if args.task:
        print_banner(state)
        return run_full_pipeline(state, " ".join(args.task))

    rc = interactive_repl(state)
    save_config(state)
    return rc


if __name__ == "__main__":
    sys.exit(main())