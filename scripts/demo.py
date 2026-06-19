"""End-to-end demo. Runs every fixture case through the harness and then walks the
full approval arc, including the gate refusal — all without a live LLM.

    python scripts/demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Windows consoles default to cp1252, which raises UnicodeEncodeError when printing
# non-ASCII fixture messages (e.g. the original Traditional Chinese requests). Force
# UTF-8 on stdout/stderr so the demo runs cleanly regardless of platform/locale.
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging  # noqa: E402

from app.fixtures_loader import load_fixtures, load_sample_requests  # noqa: E402
from app.harness.runtime import AgentHarness, ApprovalGateError  # noqa: E402
from app.planner.rule_based import RuleBasedPlanner  # noqa: E402
from app.schemas.output import AgentRunRequest  # noqa: E402

# The demo prints its own curated, readable trace, so quiet the harness's stdout
# logging (INFO) to avoid interleaving. This MUST run after importing app, since
# importing the package configures logging at INFO. The logger stays fully active
# for the server / Docker, where the structured log IS the trace.
logging.getLogger("procurement").setLevel(logging.WARNING)


def _rule(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def main() -> None:
    fixtures = load_fixtures("fixtures")
    harness = AgentHarness(planner=RuleBasedPlanner(), fixtures=fixtures)

    _rule("PART 1 -- all five fixture cases (deterministic, no LLM)")
    for case in load_sample_requests("fixtures"):
        resp = harness.run(
            AgentRunRequest(
                message=case["message"], department=case["department"], user_id=case["user_id"]
            )
        )
        print(f"\n[{case['id']}]  expected: {case['expected_behavior']}")
        print(f"  message : {case['message']}")
        print(f"  -> action={resp.decision.action.value}  status={resp.status.value}  "
              f"risk={resp.decision.risk_level.value}")
        print(f"  -> rules={resp.decision.triggered_rules or '[]'}  "
              f"missing={resp.decision.missing_fields or '[]'}")
        print(f"  -> reason: {resp.decision.reason}")
        for t in resp.tool_calls:
            print(f"       - {t.tool}: {t.status}")

    _rule("PART 2 -- approval arc: run -> NEEDS_APPROVAL -> /approve -> SUBMITTED")
    started = harness.run(
        AgentRunRequest(message="Please buy 2 MacBook Pro for engineering.", department="engineering")
    )
    print(f"run     -> {started.status.value}  (run_id={started.run_id})")

    print("\nattempt direct submit_to_erp BEFORE approval (must be refused):")
    try:
        harness.submit_to_erp(started.run_id)
        print("  !! GATE FAILED -- submit was allowed")
    except ApprovalGateError as exc:
        print(f"  [OK] refused: {exc}")

    approved = harness.approve(started.run_id)
    print(f"\napprove -> {approved.status.value}  "
          f"po={approved.draft_po.po_number} ({approved.draft_po.status})")
    print("trace:")
    for t in approved.tool_calls:
        flag = "ok " if t.ok else "REFUSED"
        print(f"  [{flag}] {t.tool}: {t.status}")


if __name__ == "__main__":
    main()
