"""Stages 8a/8b visual + LFL blocking findings."""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from _common import (
    CheckResult, GYM, list_drafts, load_yaml, bucket_to_result,
)


def _hydrated_yaml(draft: Path) -> Path | None:
    cands = list(draft.glob("world_v*.yaml"))
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


_IMG_URL_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_NAMESPACE_RE = re.compile(r"^/media/[^/]+/[^/]+/")


def image_urls_follow_namespace_convention() -> CheckResult:
    """S8aC2 — markdown image URLs follow `/media/{owner}/{repo}/...`."""
    pf, ff, na = [], [], []
    for draft in list_drafts():
        sk = _hydrated_yaml(draft)
        if not sk:
            na.append(draft.name); continue
        try:
            text = sk.read_text()
        except Exception:
            ff.append(draft.name); continue
        urls = _IMG_URL_RE.findall(text)
        # Filter out http(s) and data: URLs — only check relative paths
        local = [u for u in urls if not u.startswith(("http://", "https://", "data:"))]
        if not local:
            na.append(draft.name); continue
        # lint-ignore comment opts out of this check at file level
        if re.search(r"#\s*lint-ignore:\s*BROKEN_IMAGE_URL\b", text):
            na.append(draft.name); continue
        bad = [u for u in local if not _NAMESPACE_RE.match(u)]
        (ff if bad else pf).append(draft.name)
    return bucket_to_result(
        "image_urls_follow_the_gym_s_namespace_convention", pf, ff, na,
        evidence_extra=["Greps `![alt](url)` markdown image refs; accepts /media/<owner>/<repo>/… local URLs."],
    )


def no_bare_relative_paths_in_rendered_content() -> CheckResult:
    """S8aC3 — no `![](relative/path.png)` (without leading slash) in wiki/README content."""
    BARE = re.compile(r"!\[[^\]]*\]\((?!/|https?://|data:)([^)]+)\)")
    pf, ff, na = [], [], []
    for draft in list_drafts():
        sk = _hydrated_yaml(draft)
        if not sk:
            na.append(draft.name); continue
        try:
            text = sk.read_text()
        except Exception:
            ff.append(draft.name); continue
        # opt out
        if re.search(r"#\s*lint-ignore:\s*BROKEN_IMAGE_URL\b", text):
            na.append(draft.name); continue
        hits = BARE.findall(text)
        if not hits and "![" not in text:
            na.append(draft.name); continue
        (ff if hits else pf).append(draft.name)
    return bucket_to_result(
        "no_bare_relative_paths_in_any_agent_rendered_content", pf, ff, na,
        evidence_extra=["Greps image refs whose URL doesn't start with `/`, `http(s)://`, or `data:`."],
    )


def embedded_media_blobs_decode() -> CheckResult:
    """S8aC4 — every `content_base64:` blob decodes cleanly."""
    pf, ff, na = [], [], []
    for draft in list_drafts():
        sk = _hydrated_yaml(draft)
        if not sk:
            na.append(draft.name); continue
        doc = load_yaml(sk) or {}
        blobs: list[str] = []
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "content_base64" and isinstance(v, str):
                        blobs.append(v)
                    walk(v)
            elif isinstance(o, list):
                for v in o: walk(v)
        walk(doc)
        if not blobs:
            na.append(draft.name); continue
        bad = 0
        for b in blobs:
            try:
                base64.b64decode(b, validate=True)
            except Exception:
                bad += 1
        (ff if bad else pf).append(draft.name)
    return bucket_to_result(
        "embedded_media_blobs_decode_match_an_allowed_mime_type", pf, ff, na,
        evidence_extra=["Decodes every `content_base64:` field via base64.b64decode(..., validate=True)."],
    )


def blocking_lint_findings_clean() -> CheckResult:
    """LFLC3 — `lint_findings.json` (if present) has zero blocking findings."""
    pf, ff, na = [], [], []
    BLOCKING_KEYS = ("COVERAGE_", "BROKEN_IMAGE_URL", "MEDIA_URL_CASE_MISMATCH", "WIKI_IMAGE_CONFLICT")
    for draft in list_drafts():
        candidates = list(draft.glob("lint_findings*.json")) + list(draft.glob("findings*.json"))
        if not candidates:
            na.append(draft.name); continue
        try:
            data = json.loads(candidates[0].read_text())
        except Exception:
            ff.append(draft.name); continue
        # Findings might be a list of {category, ...} or a dict; flatten strings
        flat = json.dumps(data)
        blocking = any(b in flat for b in BLOCKING_KEYS)
        (ff if blocking else pf).append(draft.name)
    return bucket_to_result(
        "has_zero_unresolved_blocking_findings_any_suppression", pf, ff, na,
        evidence_extra=[f"Blocking categories: {BLOCKING_KEYS}."],
    )


CHECKS = [
    ("stages_8a_8b_visual_findings.image_urls_follow_the_gym_s_namespace_convention", image_urls_follow_namespace_convention),
    ("stages_8a_8b_visual_findings.no_bare_relative_paths_in_any_agent_rendered_content", no_bare_relative_paths_in_rendered_content),
    ("stages_8a_8b_visual_findings.embedded_media_blobs_decode_match_an_allowed_mime_type", embedded_media_blobs_decode),
    ("reward_lint_fix_loop.has_zero_unresolved_blocking_findings_any_suppression", blocking_lint_findings_clean),
]
