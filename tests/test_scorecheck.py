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


# ---- seal / verify (integrity: corruption/edit detection) ----
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


def test_json_array_adapter_happy_and_bad(tmp_path):
    import pytest
    from scorecheck.adapters import json_array, json_map, AdapterError
    expected = {"a": "resolved", "b": "unresolved"}
    (tmp_path / "arr.json").write_text(
        '[{"id":"a","outcome":"resolved"},{"id":"b","outcome":"unresolved"}]'
    )
    assert json_array(str(tmp_path / "arr.json")) == expected
    # array-shaped sibling of jsonl agrees with json_map on the same logical content
    (tmp_path / "map.json").write_text('{"a":"resolved","b":"unresolved"}')
    assert json_array(str(tmp_path / "arr.json")) == json_map(str(tmp_path / "map.json"))
    # a JSON object (not an array) is rejected cleanly
    (tmp_path / "obj.json").write_text('{"id":"a","outcome":"resolved"}')
    with pytest.raises(AdapterError, match="array"):
        json_array(str(tmp_path / "obj.json"))
    # a record missing 'outcome' is rejected cleanly
    (tmp_path / "missing.json").write_text('[{"id":"a"}]')
    with pytest.raises(AdapterError, match="id.*outcome"):
        json_array(str(tmp_path / "missing.json"))


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


# ---- G4 Prove-It regressions: the adversarial breaks are closed ----
def test_g4_lowrate_fabrication_now_flagged():
    """FALSE-NEGATIVE break: claim 0.40% when raw is 0.00% used to pass REPRODUCED (fixed 0.5pp tolerance)."""
    source = {f"i{n}": "unresolved" for n in range(1000)}             # 0.00%
    claim = {"name": "lowrate", "positive": "resolved", "value_x10000": 40, "published": dict(source)}
    assert adjudicate(claim, source)["verdict"] == DID_NOT_REPRODUCE


def test_g4_two_percent_inflation_now_flagged():
    """FALSE-NEGATIVE break: 25.49% vs 25.00% (0.49pp ≈ 2% rel) passed under the old fixed tolerance."""
    source = {f"i{n}": ("resolved" if n < 250 else "unresolved") for n in range(1000)}   # 25.00%
    claim = {"name": "infl", "positive": "resolved", "value_x10000": 2549, "published": dict(source)}
    assert adjudicate(claim, source)["verdict"] == DID_NOT_REPRODUCE


def test_g4_legit_rounding_still_reproduces():
    """Don't over-correct: a vendor reporting 25.00% when exact is 25.04% must still REPRODUCE."""
    source = {f"i{n}": ("resolved" if n < 2504 else "unresolved") for n in range(10000)}  # 25.04%
    claim = {"name": "round", "positive": "resolved", "value_x10000": 2500, "published": dict(source)}
    assert adjudicate(claim, source)["verdict"] == REPRODUCED


def test_g4_outcome_case_and_whitespace_no_longer_false_positive():
    """FALSE-POSITIVE break: honest claim with cosmetic case/whitespace diffs was flagged CHERRY-PICKED."""
    source = {"a": "resolved", "b": "unresolved"}
    published = {"a": "Resolved ", "b": "\tUNRESOLVED"}               # same truth, cosmetic only
    claim = {"name": "casing", "positive": "resolved", "value_x10000": 5000, "published": published}
    assert adjudicate(claim, source)["verdict"] == REPRODUCED


def test_g4_seal_forgery_caught_by_rederive_from_inputs(tmp_path):
    """SEAL break: forging the verdict + recomputing the unkeyed root passes the corruption check —
    but RE-DERIVING from the committed inputs catches it (the honest verification path)."""
    from scorecheck.seal import _root
    from scorecheck.cli import main
    src = {"a": "resolved", "b": "unresolved"}
    claim = {"name": "x", "positive": "resolved", "value_x10000": 5000, "published": dict(src)}
    receipt = tmp_path / "r.json"
    seal(adjudicate(claim, src), src, claim, str(receipt), str(tmp_path / "l.jsonl"))
    r = json.loads(receipt.read_text())
    r["scorecard"]["verdict"] = CHERRY_PICKED                        # forge the verdict
    r["root"] = _root(r["scorecard"], r["inputs_sha256"])           # attacker recomputes the unkeyed root
    receipt.write_text(json.dumps(r))
    assert verify_receipt(str(receipt))[0]                           # corruption check still passes (honest limit)
    cf = tmp_path / "c.json"; cf.write_text(json.dumps(claim))
    lf = tmp_path / "logs.json"; lf.write_text(json.dumps(src))      # json_map
    # re-derive from the real inputs → the forged verdict does NOT reproduce → exit 1
    assert main(["verify", "--receipt", str(receipt), "--claim", str(cf), "--logs", str(lf),
                 "--harness", "json_map"]) == 1


def test_g4_proof_binding_catches_swapped_logs(tmp_path, monkeypatch):
    """PROOF break: pointing `prove` at a different logs file with the SAME rate used to PASS;
    the source-hash binding now catches the swap → REFUSE."""
    import os, sys
    from scorecheck.cli import main
    monkeypatch.setenv("PATH", os.path.dirname(sys.executable) + os.pathsep + os.environ["PATH"])
    src = {f"i{n}": ("resolved" if n < 5 else "unresolved") for n in range(10)}   # 50%
    claim = {"name": "x", "positive": "resolved", "value_x10000": rate_x10000(src, "resolved"),
             "published": dict(src)}
    cf = tmp_path / "c.json"; cf.write_text(json.dumps(claim))
    logs = tmp_path / "logs.json"; logs.write_text(json.dumps(src))
    receipt = tmp_path / "r.json"
    assert main(["adjudicate", "--claim", str(cf), "--logs", str(logs), "--harness", "json_map",
                 "--receipt", str(receipt), "--ledger", str(tmp_path / "l.jsonl")]) == 0
    assert main(["prove", "--receipt", str(receipt)]) == 0          # honest → PASS
    swapped = {f"j{n}": ("resolved" if n < 5 else "unresolved") for n in range(10)}   # diff IDs, same 50%
    logs.write_text(json.dumps(swapped))
    assert main(["prove", "--receipt", str(receipt)]) == 2          # source-binding catches the swap


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
