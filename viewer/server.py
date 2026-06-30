"""Gym Audit Viewer — small FastAPI app to browse audit sessions in a browser.

Usage:
    uv run python audit/viewer/server.py [--port 8765] [--sessions-dir <path>]

The server reads audit session directories (each containing 04-scored.json)
from `audit/viewer/sessions/` and serves a single-page UI for browsing
results by category and check.
"""
from __future__ import annotations

import argparse
import json
import os
import webbrowser
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

VIEWER_DIR = Path(__file__).resolve().parent
AUDIT_REPO = VIEWER_DIR.parent          # standalone-audit repo root
AUDIT_DIR = AUDIT_REPO                  # backwards-compat alias used elsewhere in this file
DEFAULT_SESSIONS_DIR = AUDIT_REPO / "sessions"
DEFAULT_RUBRIC_PATH = AUDIT_REPO / "rubric.yaml"
DEFAULT_LIFECYCLE_PATH = AUDIT_REPO / "lifecycle_rubric.yaml"

app = FastAPI(title="Gym Audit Viewer")

# Resolved at startup
SESSIONS_DIR: Path = DEFAULT_SESSIONS_DIR
RUBRIC_PATH: Path = DEFAULT_RUBRIC_PATH
LIFECYCLE_PATH: Path = DEFAULT_LIFECYCLE_PATH
RUBRIC_INDEX: dict[str, dict[str, Any]] = {}  # check_id → metadata
LIFECYCLE_DATA: dict[str, Any] = {}            # parsed lifecycle_rubric.yaml


def _flatten_rubric(rubric_path: Path) -> dict[str, dict[str, Any]]:
    """Parse rubric.yaml and produce a flat lookup keyed by check_id.

    Each entry exposes: category_id, category_name, principle,
    detector (method + steps), levels, baseline_example, baseline_status,
    note, load_bearing.
    """
    if not rubric_path.exists():
        return {}
    rubric = yaml.safe_load(rubric_path.read_text())

    load_bearing_ids = set()
    for full_id in rubric.get("load_bearing_meta_checks", {}).get("ids", []) or []:
        load_bearing_ids.add(full_id.split(".")[-1])

    out: dict[str, dict[str, Any]] = {}

    for cat in rubric.get("categories", []) or []:
        cat_id = cat.get("id")
        cat_name = cat.get("id", "").replace("_", " ").title()
        cat_scope = cat.get("scope", "environment")  # default to environment
        for c in (cat.get("checks") or []) + (cat.get("rule_checks") or []) + (cat.get("infrastructure_checks") or []):
            cid = c.get("id")
            if not cid:
                continue
            out[cid] = {
                "category_id": cat_id,
                "category_name": cat_name,
                "category_scope": cat_scope,
                "principle": c.get("principle"),
                "detector": c.get("detector"),
                "levels": c.get("levels"),
                "baseline_example": c.get("baseline_example"),
                "baseline_rule": c.get("baseline_rule"),
                "baseline_status": c.get("baseline_status"),
                "example_defect": c.get("example_defect"),
                "note": c.get("note"),
                "domain_specific": bool(c.get("domain_specific")),
                "load_bearing": cid in load_bearing_ids,

            }

    for c in rubric.get("cross_cutting") or []:
        cid = c.get("id")
        if not cid:
            continue
        out[cid] = {
            "category_id": "cross_cutting",
            "category_name": "Cross-cutting",
            "principle": c.get("principle"),
            "detector": c.get("detector"),
            "levels": c.get("levels"),
            "baseline_example": c.get("baseline_example"),
            "note": c.get("note"),
            "domain_specific": False,
            "load_bearing": False,
            
        }

    return out


def _list_session_dirs() -> list[Path]:
    """Top-level session directories under SESSIONS_DIR.

    Each child folder containing 04-scored.json is one session. Sorted by
    mtime newest-first.
    """
    if not SESSIONS_DIR.exists():
        return []
    return sorted(
        [p for p in SESSIONS_DIR.iterdir()
         if p.is_dir() and (p / "04-scored.json").exists()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _resolve_session_dir(session_id: str) -> Path:
    """Resolve a session ID (single directory name) safely under SESSIONS_DIR."""
    # Reject anything that would escape SESSIONS_DIR.
    if "/" in session_id or "\\" in session_id or session_id in ("", ".", ".."):
        raise HTTPException(status_code=400, detail="Invalid session id")
    target = SESSIONS_DIR / session_id
    if not target.is_dir() or not (target / "04-scored.json").exists():
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return target


def _load_session(session_id: str) -> dict[str, Any]:
    return json.loads((_resolve_session_dir(session_id) / "04-scored.json").read_text())


@app.get("/api/sessions")
def list_sessions() -> list[dict[str, Any]]:
    out = []
    for p in _list_session_dirs():
        try:
            data = json.loads((p / "04-scored.json").read_text())
            out.append({
                "id": p.name,
                "target_gym": data.get("target_gym", p.name),
                "audited_at": data.get("audited_at", ""),
                "overall_score": data.get("overall_score"),
                "verdict": data.get("verdict", ""),
            })
        except Exception as e:
            out.append({"id": p.name, "error": str(e)})
    return out


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    return _load_session(session_id)


@app.get("/api/rubric")
def get_rubric() -> dict[str, Any]:
    """Return per-check rubric metadata indexed by check_id.

    Frontend uses this to render the expanded 'Details' section under each
    check card: what is checked, how it's checked, what each level means,
    why it matters, baseline reference, skip conditions.
    """
    return RUBRIC_INDEX


@app.get("/api/lifecycle-rubric")
def get_lifecycle_rubric() -> dict[str, Any]:
    """Return the phase → stage → checks tree parsed from lifecycle_rubric.yaml.

    Each check carries: id, scope (per-task/per-stage/per-batch/gym-wide),
    what, why, suggestion. Frontend uses this to render the phase/stage
    navigation + per-check detail cards.
    """
    if not LIFECYCLE_DATA:
        raise HTTPException(status_code=404, detail="lifecycle_rubric.yaml not loaded")
    return LIFECYCLE_DATA


@app.get("/api/lifecycle-results/{session_id}")
def get_lifecycle_results(session_id: str) -> dict[str, Any]:
    """Overlay session evaluation results onto the lifecycle rubric structure.

    Returns a flat map: stage_id.check_id → {level, score, evidence, failing_tasks, passing_tasks}
    when the session contains data keyed by lifecycle check IDs; otherwise empty.

    For now, sessions are keyed by the older category rubric. This endpoint
    returns an empty overlay until an audit run is executed against the
    lifecycle rubric. The frontend treats absence as "not yet evaluated."
    """
    _ = _resolve_session_dir(session_id)  # validates path
    # Placeholder: session JSON layout for lifecycle results is TBD.
    # Once an audit pipeline emits per-stage/per-check evaluations, populate
    # this from a `lifecycle_evaluations` block in 04-scored.json.
    return {"session_id": session_id, "evaluations": {}}


@app.get("/api/checks-md")
def get_checks_md() -> dict[str, Any]:
    """Return the per-check reference doc (audit/CHECKS.md) rendered as HTML."""
    checks_md_path = AUDIT_DIR / "CHECKS.md"
    if not checks_md_path.exists():
        raise HTTPException(status_code=404, detail="CHECKS.md not found")

    raw = checks_md_path.read_text()
    try:
        from markdown_it import MarkdownIt
        md = MarkdownIt("commonmark", {"breaks": False, "html": False}).enable("table")
        html = md.render(raw)
    except Exception:
        # Fallback: serve as preformatted text
        html = f"<pre>{raw.replace('<', '&lt;').replace('>', '&gt;')}</pre>"

    return {"html": html, "raw_length": len(raw)}


@app.get("/api/asset-version")
def get_asset_version() -> dict[str, int]:
    """Return mtime-based cache-busters for the SPA's JS + CSS."""
    def _mt(name: str) -> int:
        p = VIEWER_DIR / name
        return int(p.stat().st_mtime) if p.exists() else 0
    return {"app": _mt("app.js"), "style": _mt("style.css")}


@app.get("/")
def index():
    # Prevent the browser caching the entry page so the cache-buster always re-runs.
    return FileResponse(VIEWER_DIR / "index.html", headers={"Cache-Control": "no-cache, no-store"})


# Serve static (CSS / JS) at /static/*
app.mount("/static", StaticFiles(directory=VIEWER_DIR), name="static")


def main():
    global SESSIONS_DIR, RUBRIC_PATH, LIFECYCLE_PATH, RUBRIC_INDEX, LIFECYCLE_DATA
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--sessions-dir", default=str(DEFAULT_SESSIONS_DIR))
    parser.add_argument("--rubric", default=str(DEFAULT_RUBRIC_PATH))
    parser.add_argument("--lifecycle", default=str(DEFAULT_LIFECYCLE_PATH))
    parser.add_argument("--no-browser", action="store_true",
                        help="Don't prompt to open the browser (useful for headless / background use)")
    args = parser.parse_args()

    SESSIONS_DIR = Path(args.sessions_dir).resolve()
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    RUBRIC_PATH = Path(args.rubric).resolve()
    RUBRIC_INDEX = _flatten_rubric(RUBRIC_PATH)
    LIFECYCLE_PATH = Path(args.lifecycle).resolve()
    if LIFECYCLE_PATH.exists():
        LIFECYCLE_DATA = yaml.safe_load(LIFECYCLE_PATH.read_text()) or {}
    else:
        LIFECYCLE_DATA = {}
    lc_checks = sum(len(s.get("checks", [])) for p in LIFECYCLE_DATA.get("phases", []) for s in p.get("stages", []))
    url = f"http://{args.host}:{args.port}"
    print(f"Sessions dir:    {SESSIONS_DIR}")
    print(f"Rubric:          {RUBRIC_PATH} ({len(RUBRIC_INDEX)} indexed checks)")
    print(f"Lifecycle:       {LIFECYCLE_PATH} ({lc_checks} indexed checks)" if LIFECYCLE_DATA else "Lifecycle:       (not loaded)")
    print(f"Listening on {url}")

    if not args.no_browser:
        # Prompt loop on a daemon thread — pressing Enter (re)opens the browser,
        # while uvicorn runs on the main thread and stays responsive to Ctrl-C.
        import threading

        def _prompt_loop():
            # Small delay so the prompt prints below uvicorn's startup banner.
            import time
            time.sleep(0.6)
            while True:
                try:
                    line = input(f"\nPress Enter to open {url} in your browser (Ctrl-C to quit) ▸ ")
                except EOFError:
                    return  # stdin closed (e.g. headless background run)
                if line.strip().lower() in ("q", "quit", "exit"):
                    print("Bye — stop the server with Ctrl-C.")
                    return
                webbrowser.open(url)

        threading.Thread(target=_prompt_loop, daemon=True).start()

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
