"""Adapters: raw benchmark run-logs → reconcile's ``{stable_id: outcome}`` source format.

This is the project's load-bearing generality test (kill-criterion b): if real harness logs can't be
mapped without bespoke per-vendor parsers, the value prop collapses. Kept deliberately thin — one small
function per harness family. The canonical SWE-bench case is ~3 lines (verified on a real results.json).
"""
from __future__ import annotations

import json
from pathlib import Path


def swebench(logs_path: str, positive: str = "resolved") -> dict:
    """SWE-bench ``results.json``: ``generated`` (all attempted) + ``resolved`` (passed) → {id: outcome}."""
    raw = json.loads(Path(logs_path).read_text(encoding="utf-8"))
    generated, won = set(raw["generated"]), set(raw["resolved"])
    return {iid: (positive if iid in won else "unresolved") for iid in generated}


def jsonl(logs_path: str) -> dict:
    """Generic: one JSON object per line carrying ``id`` + ``outcome`` → {id: outcome}."""
    out = {}
    for line in Path(logs_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        out[str(o["id"])] = str(o["outcome"])
    return out


ADAPTERS = {"swebench": swebench, "jsonl": jsonl}
