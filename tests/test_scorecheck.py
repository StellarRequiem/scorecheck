"""scorecheck's contract: it must catch selective reporting (CHERRY-PICKED) and number-drift
(DID-NOT-REPRODUCE) while passing honest claims (REPRODUCED) — on REAL benchmark data — and the
verdict must be sealed so a doctored receipt is caught. Exercised against a real SWE-bench results file."""
import json
from pathlib import Path

from scorecheck.adapters import swebench
from scorecheck.adjudicate import (adjudicate, exit_code, rate_x10000,
                                   REPRODUCED, DID_NOT_REPRODUCE, CHERRY_PICKED)
from scorecheck.seal import seal, verify_receipt

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "swebench_rag_gpt4_results.json"
SRC = swebench(str(FIX))            # real: 500 instances, 14 resolved
LOSSES = [i for i, o in SRC.items() if o != "resolved"]


def honest_claim() -> dict:
    return {"name": "rag_gpt4", "metric": "resolve_rate", "positive": "resolved",
            "value_x10000": rate_x10000(SRC, "resolved"), "published": dict(SRC)}


# ---- the three verdicts, on real data ----
def test_honest_is_reproduced():
    assert adjudicate(honest_claim(), SRC)["verdict"] == REPRODUCED


def test_dropped_failures_is_cherry_picked():
    pub = {k: v for k, v in SRC.items() if k not in LOSSES[:40]}  # hide 40 losses (MISSING)
    pub[LOSSES[40]] = "resolved"                                   # report 1 loss as a win (FLIPPED)
    claim = {"name": "x", "positive": "resolved", "value_x10000": 800, "published": pub}
    card = adjudicate(claim, SRC)
    assert card["verdict"] == CHERRY_PICKED
    assert card["reconcile"]["missing"] == 40 and card["reconcile"]["flipped"] == 1


def test_fabricated_instance_is_cherry_picked():
    claim = honest_claim()
    claim["published"] = {**claim["published"], "fabricated-instance-9999": "resolved"}  # EXTRA
    card = adjudicate(claim, SRC)
    assert card["verdict"] == CHERRY_PICKED and card["reconcile"]["extra"] == 1


def test_number_drift_is_did_not_reproduce():
    claim = honest_claim()                       # reconcile clean…
    claim["value_x10000"] += 1500                # …but the headline number is inflated by 15 points
    assert adjudicate(claim, SRC)["verdict"] == DID_NOT_REPRODUCE


# ---- seal / verify (tamper-evidence) ----
def test_seal_verify_roundtrip_and_tamper(tmp_path):
    card = adjudicate(honest_claim(), SRC)
    receipt, ledger = tmp_path / "r.json", tmp_path / "l.jsonl"
    root = seal(card, SRC, honest_claim(), str(receipt), str(ledger))
    ok, msg = verify_receipt(str(receipt))
    assert ok and root in msg
    # tamper: flip the sealed verdict in the receipt → root must no longer re-derive
    r = json.loads(receipt.read_text())
    r["scorecard"]["verdict"] = CHERRY_PICKED
    receipt.write_text(json.dumps(r))
    ok2, _ = verify_receipt(str(receipt))
    assert not ok2


# ---- G3: adapter generality (the kill-criterion: thin, no bespoke parsers) ----
def test_csv_and_json_map_adapters_agree(tmp_path):
    from scorecheck.adapters import csv as csv_adapter, json_map
    (tmp_path / "r.csv").write_text("id,outcome\na,resolved\nb,unresolved\n")
    (tmp_path / "r.json").write_text('{"a": "resolved", "b": "unresolved"}')
    expected = {"a": "resolved", "b": "unresolved"}
    assert csv_adapter(str(tmp_path / "r.csv")) == expected
    assert json_map(str(tmp_path / "r.json")) == expected


def test_jsonl_adapter_happy_and_bad_line(tmp_path):
    import pytest
    from scorecheck.adapters import jsonl, AdapterError
    (tmp_path / "ok.jsonl").write_text('{"id":"a","outcome":"resolved"}\n\n{"id":"b","outcome":"x"}\n')
    assert jsonl(str(tmp_path / "ok.jsonl")) == {"a": "resolved", "b": "x"}
    (tmp_path / "bad.jsonl").write_text('{"id":"a"}\n')        # missing 'outcome'
    with pytest.raises(AdapterError, match="line 1"):
        jsonl(str(tmp_path / "bad.jsonl"))


def test_adapter_errors_are_clean(tmp_path):
    import pytest
    from scorecheck.adapters import AdapterError, swebench, json_map, csv as csv_adapter
    with pytest.raises(AdapterError, match="not found"):
        swebench(str(tmp_path / "nope.json"))
    (tmp_path / "bad.json").write_text('["not", "a", "map"]')
    with pytest.raises(AdapterError, match="id: outcome"):
        json_map(str(tmp_path / "bad.json"))
    (tmp_path / "wrongcols.csv").write_text("id,result\na,resolved\n")   # no 'outcome' column
    with pytest.raises(AdapterError, match="outcome"):
        csv_adapter(str(tmp_path / "wrongcols.csv"))
    (tmp_path / "notswe.json").write_text('{"foo": 1}')                  # missing generated/resolved
    with pytest.raises(AdapterError, match="SWE-bench"):
        swebench(str(tmp_path / "notswe.json"))


def test_empty_logs_rate_is_zero():
    assert rate_x10000({}, "resolved") == 0


# ---- G3: proof-carrying (verity prove re-runs the recompute) ----
def test_proof_claim_shape():
    from scorecheck.adjudicate import build_proof_claim
    card = adjudicate(honest_claim(), SRC)
    pc = build_proof_claim(card, "fixtures/x.json", "swebench", "resolved")
    assert pc["proof"].startswith("scorecheck recompute --logs fixtures/x.json")
    assert pc["value"] == card["recomputed_from_source_x10000"] and pc["tolerance"] == 0


def test_recompute_cli_emits_parseable_line(capsys):
    from scorecheck.cli import main
    assert main(["recompute", "--logs", str(FIX), "--harness", "swebench", "--positive", "resolved"]) == 0
    out = capsys.readouterr().out
    assert f"recomputed_x10000: {rate_x10000(SRC, 'resolved')}" in out


def test_prove_passes_then_catches_a_number_that_does_not_rederive(tmp_path, monkeypatch):
    """The flagship G3 loop: adjudicate seals a proof; `prove` re-runs `scorecheck recompute` via verity
    and PASSES only if the sealed number actually re-derives from the raw logs — else REFUSE."""
    import os, sys, json as _json
    from scorecheck.cli import main
    monkeypatch.setenv("PATH", os.path.dirname(sys.executable) + os.pathsep + os.environ["PATH"])
    claim_f = tmp_path / "claim.json"
    claim_f.write_text(_json.dumps(honest_claim()))
    receipt = tmp_path / "r.json"
    assert main(["adjudicate", "--claim", str(claim_f), "--logs", str(FIX), "--harness", "swebench",
                 "--receipt", str(receipt), "--ledger", str(tmp_path / "l.jsonl")]) == 0
    # honest number re-derives from the raw logs → PASS
    assert main(["prove", "--receipt", str(receipt)]) == 0
    # tamper the sealed number → the recompute no longer matches → REFUSE
    r = _json.loads(receipt.read_text())
    r["scorecard"]["recomputed_from_source_x10000"] += 500
    receipt.write_text(_json.dumps(r))
    assert main(["prove", "--receipt", str(receipt)]) == 2


# ---- invariants ----
def test_exit_code_ladder():
    assert (exit_code(REPRODUCED), exit_code(DID_NOT_REPRODUCE), exit_code(CHERRY_PICKED)) == (0, 1, 2)


def test_scorecard_is_float_free():
    card = adjudicate(honest_claim(), SRC)

    def no_float(o):
        assert not isinstance(o, float), o
        if isinstance(o, dict):
            [no_float(v) for v in o.values()]
        if isinstance(o, list):
            [no_float(v) for v in o]

    no_float(card)
