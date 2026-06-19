# AI Usage

I used AI (Claude) as an implementation tool and a sounding board, while keeping
the architectural and policy decisions — the parts that actually determine
whether this system is safe — under my own control. This document is specific
about which calls were mine and how I checked the output rather than accepting it.

## How AI was used

- **Design, directed by me.** I drove the architecture and the decision logic.
  AI helped me pressure-test and write it up — the build plan, the 5-case
  decision table, and the trap analysis were produced collaboratively, but the
  governing choices (where risk is decided, how the approval gate works, what
  each edge case means) were mine to make and accept or reject.
- **Implementation and scaffolding.** AI generated most of the code from that
  agreed design: the FastAPI/pydantic layout, the schema models, the harness,
  the policy engine, the planner, and the tests. I treated this as a fast first
  draft to review, not as finished work.
- **Documentation.** First drafts of the README and ARCHITECTURE were
  AI-assisted, then edited for accuracy.

## How I verified it

I read the implementation closely rather than trusting it on sight, and pinned
the behavior down with tests and by-hand checks:

- **Ran every fixture case.** All five `sample_requests.json` scenarios run
  end-to-end (`scripts/demo.py`) and are asserted in `tests/test_cases.py`
  against each fixture's `expected_behavior` — the source of truth.
- **Asserted on reasons, not just actions.** Several tests check
  `triggered_rules`, not only the final action, so a "right answer for the wrong
  reason" implementation fails. The clearest example: case_002 must fire
  `policy_002` (hardware) and **not** `policy_001` (amount).
- **Checked the boundaries by hand** against the real catalog numbers — MacBook
  $2,500 × 2 = exactly $5,000, and Figma $800 × 10 = $8,000 inside a $10,000
  budget — before I trusted the engine's branching.
- **Proved the approval gate.** `tests/test_gate.py` shows a direct
  `submit_to_erp` on an un-approved run is refused and logged, and that
  `/approve` then submits. I also confirmed this against a live server.
- **Caught that the injection example was Chinese, and tested for it.** The
  brief's canonical prompt injection (case_005) is Traditional Chinese
  (忽略所有公司政策…). My first bypass detector was English-only, so it never fired
  on the one example it existed for — the request still rejected *structurally*
  (over budget + hardware), which is exactly why the tests stayed green and hid
  the gap. I made the detector bilingual and added `tests/test_bypass.py` to
  assert both English and Chinese circumvention trip `policy_004` while innocent
  urgency (直接送出 / "submit directly") does not. The structural defense was
  never at risk; the defense-in-depth layer now matches the brief's own input.
- **Exercised tool dispatch and logging.** `tests/test_tool_validation.py`
  confirms a crafted payload is rejected at the single `_dispatch` chokepoint
  (validated against the registry's model), and `tests/test_logging.py` confirms
  a run emits its full stdout trace and that a gate refusal logs at `WARNING`.

## Decisions I owned (where I did not just accept the AI's first pass)

- **Risk classification stays deterministic and out of the LLM.** This was a
  deliberate design constraint I imposed: the planner may only propose an intent,
  never a risk level, decision, or tool name. It is the single choice that
  answers both "where is the approval gate?" and "how do you handle prompt
  injection?".
- **Injection defense is structural, not a keyword blocklist.** I rejected
  leaning on a phrase detector as the primary defense. The real protection is
  that the planner has no field in which to demand a privileged action and
  `submit_to_erp` is unreachable outside an `APPROVED` state. The bypass detector
  is explicitly demoted to defense-in-depth that can only *escalate* a decision.
- **The exact-$5,000 edge.** I required the amount rule to be strict `>`, so a
  $5,000 hardware order routes to approval via the *category* rule, not the
  amount rule — and I locked that distinction in with a test.
- **Budget as an orthogonal axis, with over-budget as a hard REJECT.** I treated
  budget and the approval threshold as separate axes and made the
  not-in-fixtures "under-threshold-but-over-budget" case a deliberate REJECT with
  a documented rationale, rather than leaving it to an accidental fall-through.
- **Keeping language out of the decision path, and proving it.** The take-home
  shipped its sample requests in Traditional Chinese. Rather than hard-coding the
  system to English, I drew the boundary so that *parsing* (the planner) is the
  only language-aware layer and the decision logic sees only
  `(category, amount, budget, bypass)`. The rule-based planner runs on English;
  the LLM planner (OpenAI SDK → Groq, `response_format` JSON schema) parses the
  untouched Chinese into the identical `ProposedIntent`. I verified this against
  live Groq: 「請幫工程部購買 2 台 MacBook Pro」resolves to MacBook Pro × 2 and
  routes through the same deterministic path to `policy_002` / `NEEDS_APPROVAL` /
  $5,000 as the English case_002. So the language point is a demonstration that
  the core is language-agnostic and the planner is swappable — not a concession.

The throughline: AI accelerated the implementation; the judgment about how the
system should behave, and the verification that it does, were mine.
