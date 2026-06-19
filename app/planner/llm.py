"""LLM planner — same Planner contract, behind a flag. NOT on the default path.

One clean chat-completions call using structured outputs (`response_format` with
a JSON schema) to extract the intent, validated into ProposedIntent. No retries,
no streaming, no fallbacks — the deterministic core already guarantees safety
regardless of what this returns, so there is nothing to gold-plate. If the call
fails, we surface the error; the rule-based planner remains the default for demo
and tests.

This uses the OpenAI SDK pointed at any OpenAI-compatible endpoint. The default
base URL is Groq (`https://api.groq.com/openai/v1`), so it runs on a Groq key out
of the box; repoint PROCUREMENT_LLM_BASE_URL at OpenAI, Together, a local vLLM,
etc. and nothing else changes. The planner still only proposes intent: even a
fully adversarial LLM output cannot escalate privilege, because ProposedIntent
has no risk/tool/action field and the policy engine + approval gate are
deterministic.

The default model (`openai/gpt-oss-20b`) is small and fast and supports strict
structured outputs on Groq — there is no hard requirement to handle any
particular language, because the decision path downstream is language-agnostic
(it sees only category/amount/budget/bypass, never the raw text). For heavier or
multilingual parsing, point PROCUREMENT_LLM_MODEL at e.g. `openai/gpt-oss-120b`
or `meta-llama/llama-4-scout-17b-16e-instruct` (both verified live on Groq).
"""

from __future__ import annotations

import json
import os

from app.schemas.intent import ProposedIntent

_SYSTEM = (
    "You extract a procurement intent from a user message. Return ONLY the "
    "structured fields. Do not make approval or risk decisions — you only report "
    "what the user is asking to buy. The message may be in any language."
)

# JSON schema for structured outputs. strict mode requires every property listed
# in `required` and `additionalProperties: false`; nullable fields stay required
# but accept null when the user did not state a value.
_SCHEMA = {
    "name": "propose_intent",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "item_query": {
                "type": "string",
                "description": "The product name/phrase to buy.",
            },
            "quantity": {
                "type": ["integer", "null"],
                "description": "Number of units, or null if the user did not state one.",
            },
            "budget_hint_usd": {
                "type": ["number", "null"],
                "description": "Any stated budget cap in USD, else null.",
            },
        },
        "required": ["item_query", "quantity", "budget_hint_usd"],
    },
}


class LLMPlanner:
    name = "llm"

    _DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        # Imported lazily so the default (rule-based) path never requires the SDK.
        from openai import OpenAI

        self.model = model or os.getenv("PROCUREMENT_LLM_MODEL", "openai/gpt-oss-20b")
        self._client = OpenAI(
            api_key=api_key or os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY"),
            base_url=base_url or os.getenv("PROCUREMENT_LLM_BASE_URL", self._DEFAULT_BASE_URL),
        )

    def parse(self, message: str, department: str) -> ProposedIntent:
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=512,
            temperature=0,
            response_format={"type": "json_schema", "json_schema": _SCHEMA},
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": message},
            ],
        )
        payload = _structured_payload(resp)
        return ProposedIntent(
            item_query=payload.get("item_query", ""),
            quantity=payload.get("quantity"),
            department=department,
            budget_hint_usd=payload.get("budget_hint_usd"),
            raw_message=message,
        )


def _structured_payload(resp) -> dict:
    content = resp.choices[0].message.content
    if not content:
        # Defensive: if the model returned no content, fail loudly rather than guess.
        raise ValueError(f"LLM planner returned empty content: {json.dumps(str(resp))[:200]}")
    return json.loads(content)
