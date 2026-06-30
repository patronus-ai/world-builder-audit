#!/usr/bin/env python3
"""world-builder-audit — helper launcher (non-LLM).

This is NOT the full audit. The full audit is the `/gym-audit` skill in
Claude Code, which scores all 141 checks (deterministic floor + LLM eval).
This launcher only handles the non-LLM pieces: it prompts for the gym repo
to audit (path on disk, or a git URL to clone), records the choice in
`.last_target` so the scripts and viewer pick it up, and dispatches to:

  ./audit.py            → prompt + show menu
  ./audit.py scripts    → run only the deterministic scripts (the reproducible floor)
  ./audit.py viewer     → launch the FastAPI viewer
  ./audit.py both       → deterministic scripts, then viewer

For the full audit, run `/gym-audit` in Claude Code instead.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent
LAST_TARGET = REPO / ".last_target"

# Modules the child scripts/viewer import. audit.py launches them with the same
# interpreter (sys.executable), so checking here catches a missing/uninstalled
# environment up front instead of as a nested subprocess traceback.
REQUIRED_MODULES = {
    "yaml": "pyyaml",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn[standard]",
    "markdown_it": "markdown-it-py",
}


def _check_dependencies() -> None:
    import importlib.util

    missing = sorted(
        pkg for mod, pkg in REQUIRED_MODULES.items()
        if importlib.util.find_spec(mod) is None
    )
    if not missing:
        return
    raise SystemExit(
        "Missing dependencies: " + ", ".join(missing) + "\n\n"
        f"This toolkit must be installed before running. Using {sys.executable}\n"
        "Install with either:\n"
        "  uv sync                 # creates/uses .venv, then run: uv run ./audit.py\n"
        "  pip install -e .        # into an active virtualenv\n"
    )


def _is_url(s: str) -> bool:
    return s.startswith("git@") or s.startswith("http://") or s.startswith("https://")


def _resolve_or_clone(target: str) -> Path:
    if _is_url(target):
        dest = REPO / ".cache" / "clones"
        dest.mkdir(parents=True, exist_ok=True)
        name = target.rstrip("/").split("/")[-1].removesuffix(".git")
        clone_dir = dest / name
        if clone_dir.exists():
            print(f"Reusing existing clone at {clone_dir}")
        else:
            print(f"Cloning {target} → {clone_dir} …")
            subprocess.check_call(["git", "clone", "--depth=1", target, str(clone_dir)])
        return clone_dir.resolve()
    p = Path(target).expanduser().resolve()
    if not p.exists():
        raise SystemExit(f"Path does not exist: {p}")
    return p


def _prompt_target() -> Path:
    hint = ""
    if LAST_TARGET.exists():
        hint = f" [Enter to reuse {LAST_TARGET.read_text().strip()}]"
    raw = input(f"Which gym to audit? (local path OR git URL){hint}\n> ").strip()
    if not raw and LAST_TARGET.exists():
        raw = LAST_TARGET.read_text().strip()
    if not raw:
        raise SystemExit("No target supplied — aborting.")
    target = _resolve_or_clone(raw)
    LAST_TARGET.write_text(str(target))
    print(f"Target gym: {target}\n")
    return target


def _menu() -> str:
    print("This launcher runs the non-LLM pieces only.")
    print("For the FULL audit (all 141 checks), run /gym-audit in Claude Code.\n")
    print("What would you like to do?")
    print("  1) Run deterministic scripts only — the floor (no LLM)")
    print("  2) Launch the viewer (existing sessions)")
    print("  3) Both — scripts first, then viewer")
    print("  q) Quit")
    while True:
        c = input("Choice [1/2/3/q]: ").strip().lower()
        if c in {"1", "2", "3", "q"}:
            return c


def run_scripts(target: Path) -> None:
    env = os.environ.copy()
    env["TARGET_GYM"] = str(target)
    subprocess.check_call([sys.executable, str(REPO / "scripts" / "run_all.py")], env=env)


def run_viewer(target: Path) -> None:
    env = os.environ.copy()
    env["TARGET_GYM"] = str(target)
    subprocess.check_call([sys.executable, str(REPO / "viewer" / "server.py")], env=env)


def main() -> int:
    args = sys.argv[1:]
    _check_dependencies()
    target = _prompt_target()

    if not args:
        choice = _menu()
        if choice == "q":
            return 0
        action = {"1": "scripts", "2": "viewer", "3": "both"}[choice]
    else:
        action = args[0]
        if action not in {"scripts", "viewer", "both"}:
            print(f"Unknown action: {action}", file=sys.stderr)
            print(__doc__, file=sys.stderr)
            return 2

    if action in ("scripts", "both"):
        run_scripts(target)
    if action in ("viewer", "both"):
        run_viewer(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
