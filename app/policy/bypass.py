"""Bypass-phrase detector — defense-in-depth, NOT the primary defense.

The primary prompt-injection defense is structural: the planner cannot name a
tool or set a risk level, and submit_to_erp is unreachable outside an APPROVED
run state. This detector is layered on top so that an explicit attempt to
circumvent policy (fixture policy_004) is recorded and can only *escalate* a
decision (never relax it).

It deliberately keys on policy-circumvention intent — "ignore policy", "do not
approve", "bypass" — and NOT on ordinary urgency like "submit directly" (which
appears innocently in case_002 and must not be flagged). Patterns cover English
and Chinese (Traditional + Simplified), since the brief's canonical injection
example is in Traditional Chinese; the same intent/urgency distinction holds in
both — 直接送出 ("submit directly") is innocent and must not trip the detector.
"""

from __future__ import annotations

import re

# Each pattern targets an explicit attempt to skip/override approval or policy.
# CJK text has no word boundaries, so the Chinese patterns match circumvention
# keywords within a short character window rather than using \b.
_PATTERNS = [
    # --- English ---
    re.compile(r"ignore\b.{0,25}?(polic|rule|approval|instruction)", re.IGNORECASE),
    re.compile(r"\bbypass\b", re.IGNORECASE),
    re.compile(r"override\b.{0,15}?(polic|approval|rule)", re.IGNORECASE),
    re.compile(r"skip\b.{0,15}?approval", re.IGNORECASE),
    re.compile(r"without\s+approval", re.IGNORECASE),
    re.compile(r"no\s+approval\s+(needed|required)", re.IGNORECASE),
    re.compile(r"do(?:\s+not|n['’]t)\s+(?:get\s+|seek\s+)?approv", re.IGNORECASE),
    re.compile(r"direct\s+order", re.IGNORECASE),
    # --- Chinese (Traditional + Simplified) ---
    re.compile(r"忽略.{0,10}(政策|規定|规定|核准|審批|审批|流程)"),   # ignore policy/approval
    re.compile(r"(不需|不用|無需|无需|毋需|無須|无须|免).{0,4}(核准|審批|审批|批准)"),  # no approval needed
    re.compile(r"(跳過|跳过|略過|略过|繞過|绕过).{0,6}(核准|審批|审批|流程|政策)"),  # skip/bypass approval
    re.compile(r"(不要|別|别|勿|無須|无须).{0,4}核准"),              # do not approve
]


def detect_bypass(message: str) -> bool:
    if not message:
        return False
    return any(p.search(message) for p in _PATTERNS)
