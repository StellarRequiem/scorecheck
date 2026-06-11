"""scorecheck — adjudicate a published benchmark claim against its raw run-logs.

Returns REPRODUCED / DID-NOT-REPRODUCE / CHERRY-PICKED by composing `calibration-log`'s reconcile
(selective-reporting detection) with a metric recompute, sealed into a tamper-evident receipt.
"""
from .adapters import ADAPTERS, swebench, jsonl
from .adjudicate import (adjudicate, exit_code, rate_x10000,
                         REPRODUCED, DID_NOT_REPRODUCE, CHERRY_PICKED)
from .seal import seal, verify_receipt, canonical

__version__ = "0.1.0"
__all__ = ["ADAPTERS", "swebench", "jsonl", "adjudicate", "exit_code", "rate_x10000",
           "REPRODUCED", "DID_NOT_REPRODUCE", "CHERRY_PICKED", "seal", "verify_receipt", "canonical"]
