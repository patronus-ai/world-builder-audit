"""Run every deterministic audit script and merge results into a session.

Usage:
    uv run python scripts/run_all.py [--session <session_id>] [--print-only]

Behavior:
  * Discovers every `CHECKS = [(rubric_key, fn), …]` registry in this folder.
  * Calls each runner function, collecting CheckResult objects.
  * If --session is given (or one auto-detected), writes/merges the results
    into `sessions/<session>/04-scored.json` under `lifecycle_evaluations`.
  * Always prints a one-line summary per check.

These results are 100% reproducible from the target gym's filesystem alone —
no LLM, no agent, no API. They form the deterministic floor that the
gym-audit skill uses BEFORE asking any LLM-evaluator to look at the same checks.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

# Make _common importable when this file is executed directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import CheckResult, AUDIT_REPO  # noqa: E402


SCRIPTS_DIR = Path(__file__).resolve().parent
SESSIONS_DIR = AUDIT_REPO / "sessions"


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def collect_results() -> list[dict]:
    out: list[dict] = []
    for py in sorted(SCRIPTS_DIR.glob("*.py")):
        if py.name.startswith("_") or py.name == "run_all.py":
            continue
        mod = load_module(py)
        registry = getattr(mod, "CHECKS", None)
        if not registry:
            continue
        for rubric_key, fn in registry:
            try:
                result = fn()
            except Exception as e:
                result = CheckResult(
                    check_id=rubric_key.split(".", 1)[1] if "." in rubric_key else rubric_key,
                    level="absent", score=0.0,
                    evidence=[f"Script {py.name} raised: {e!r}"],
                )
            result.source_script = f"scripts/{py.name}"
            out.append({"_rubric_key": rubric_key, **asdict(result)})
    return out


def merge_into_session(results: list[dict], session_id: str) -> Path:
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    scored = session_dir / "04-scored.json"
    data = json.loads(scored.read_text()) if scored.exists() else {"lifecycle_evaluations": {}}
    lc = data.setdefault("lifecycle_evaluations", {})
    for r in results:
        key = r.pop("_rubric_key")
        lc[key] = r
    scored.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return scored


def auto_detect_session() -> str | None:
    if not SESSIONS_DIR.exists():
        return None
    candidates = sorted(
        (p for p in SESSIONS_DIR.iterdir() if p.is_dir() and (p / "04-scored.json").exists()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0].name if candidates else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", help="Session ID to merge into (defaults to the most-recent).")
    ap.add_argument("--print-only", action="store_true", help="Don't write; just print results.")
    args = ap.parse_args()

    results = collect_results()
    print(f"Ran {len(results)} deterministic checks.\n")
    for r in results:
        key = r["_rubric_key"]
        pn = len(r.get("passing_tasks") or []) if r.get("passing_tasks") is not None else "—"
        fn = len(r.get("failing_tasks") or []) if r.get("failing_tasks") is not None else "—"
        print(f"  {key:80s}  level={r['level']:8s}  pass={pn}  fail={fn}")

    if args.print_only:
        return 0

    session = args.session or auto_detect_session()
    if not session:
        import datetime
        session = "deterministic-" + datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        print(f"\nNo existing session — creating {session}")

    out = merge_into_session(results, session)
    print(f"\nMerged into {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
