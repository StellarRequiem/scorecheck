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
