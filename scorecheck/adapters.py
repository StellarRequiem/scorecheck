"""Adapters: raw benchmark run-logs → reconcile's ``{stable_id: outcome}`` source format.

This is the project's load-bearing generality test (kill-criterion b): if real harness logs can't be
mapped without bespoke per-vendor parsers, the value prop collapses. Kept deliberately thin — one small
function per harness family. The canonical SWE-bench case is ~3 lines (verified on a real results.json).
"""
from __future__ import annotations

import csv as _csv
import json
from pathlib import Path


class AdapterError(ValueError):
    """A raw-log file is missing, unreadable, or not in the adapter's expected shape."""


def _text(logs_path: str) -> str:
    p = Path(logs_path)
    if not p.is_file():
        raise AdapterError(f"raw-logs file not found: {logs_path}")
    return p.read_text(encoding="utf-8")


def swebench(logs_path: str, positive: str = "resolved") -> dict:
    """SWE-bench ``results.json``: ``generated`` (all attempted) + ``resolved`` (passed) → {id: outcome}."""
    try:
        raw = json.loads(_text(logs_path))
        generated, won = set(raw["generated"]), set(raw["resolved"])
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise AdapterError(f"not a SWE-bench results.json (need 'generated' + 'resolved'): {e}") from e
    return {str(iid): (positive if iid in won else "unresolved") for iid in generated}


def jsonl(logs_path: str) -> dict:
    """Generic: one JSON object per line carrying ``id`` + ``outcome`` → {id: outcome}."""
    out = {}
    for n, line in enumerate(_text(logs_path).splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
            out[str(o["id"])] = str(o["outcome"])
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise AdapterError(f"jsonl line {n}: need a JSON object with 'id' + 'outcome': {e}") from e
    return out


def csv(logs_path: str) -> dict:
    """Generic CSV with an ``id`` column + an ``outcome`` column (header row) → {id: outcome}."""
    try:
        return {str(r["id"]): str(r["outcome"]) for r in _csv.DictReader(_text(logs_path).splitlines())}
    except (KeyError, TypeError) as e:
        raise AdapterError(f"CSV needs 'id' + 'outcome' columns: {e}") from e


def json_map(logs_path: str) -> dict:
    """Generic: a single JSON object mapping ``{id: outcome}`` directly → {id: outcome}."""
    try:
        raw = json.loads(_text(logs_path))
        if not isinstance(raw, dict):
            raise TypeError("expected a JSON object {id: outcome}")
    except (json.JSONDecodeError, TypeError) as e:
        raise AdapterError(f"not a JSON {{id: outcome}} map: {e}") from e
    return {str(k): str(v) for k, v in raw.items()}


ADAPTERS = {"swebench": swebench, "jsonl": jsonl, "csv": csv, "json_map": json_map}
