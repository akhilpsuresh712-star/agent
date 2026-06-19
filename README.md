# Procurement Approval Agent

A small agentic service that turns a natural-language purchase request into a
**deterministic, auditable** procurement decision: draft a PO, send it for human
approval, ask for clarification, or reject it. The agent loop, tool boundary,
approval gate, and schema validation are all hand-rolled — there is no
off-the-shelf agent framework; the harness *is* `AgentHarness`.

The natural-language layer is a first-class part of the design, not an
afterthought: the planner parses free-form requests — English and the original
Traditional Chinese fixtures alike — into a structured intent. The deliberate
seam is that this flexible NL frontend sits on a deterministic core it can
*propose to but never command*.

That seam is the design principle throughout: **the planner is untrusted.** It
proposes an *intent* only — never a risk level, a decision, or a tool name. All
risk classification is a pure function of `(category, amount, budget, bypass_flag)`
and never touches an LLM. `submit_to_erp` is structurally unreachable except from
an `APPROVED` run state.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"                              # app (editable) + test deps (pytest, httpx)
uvicorn app.main:app --reload
```

> Use `pip install -e ".[dev]"` to run **everything**: the editable install puts
> `app` on the import path (so `uvicorn app.main:app` works from any directory)
> and pulls in `pytest`/`httpx` for the test suite. To only *run the server*,
> `pip install -r requirements.txt` (runtime deps only) is enough — that's what
> the Dockerfile uses.

Example request (case_002 — hardware → needs approval):

```bash
curl -s -X POST http://127.0.0.1:8000/agent/run \
  -H 'Content-Type: application/json' \
  -d '{"message":"Please buy 2 MacBook Pro for engineering.","department":"engineering"}'
```

Then walk the approval arc with the `run_id` from the response:

```bash
curl -s -X POST http://127.0.0.1:8000/agent/runs/<run_id>/approve   # -> SUBMITTED
curl -s -X POST http://127.0.0.1:8000/agent/runs/<run_id>/reject    # -> REJECTED
```

## Demo & tests

```bash
python scripts/demo.py     # all 5 fixture cases + the approve arc + the gate refusal
pytest                     # 37 tests: cases, gate, tool validation + registry dispatch, bypass (EN+ZH), logging, output schema, API
```

Neither the demo nor the tests depend on a live LLM.

## Planner switch (rule-based default, LLM optional)

The rule-based planner is the default and needs nothing external. To use the LLM
planner (one clean chat-completions call, structured output via JSON schema,
validated):

```bash
export PROCUREMENT_PLANNER=llm
export GROQ_API_KEY=gsk_...
export PROCUREMENT_LLM_MODEL=openai/gpt-oss-20b   # optional; small + fast
pip install openai
uvicorn app.main:app
```

Or skip the `export`s: copy `.env.example` to `.env`, fill in `GROQ_API_KEY`, and
it's loaded on startup (via `python-dotenv`). A real shell `export` still wins
over the file, so the two compose cleanly.

The planner uses the **OpenAI SDK pointed at any OpenAI-compatible endpoint**.
The default base URL is Groq (`https://api.groq.com/openai/v1`), so it runs on a
Groq key out of the box; set `PROCUREMENT_LLM_BASE_URL` to repoint at OpenAI,
Together, a local vLLM, etc. with no code change. The call pins `response_format`
to the `ProposedIntent` JSON schema. The default `openai/gpt-oss-20b` parses the
original Traditional Chinese fixtures straight into the same decision path —
verified against live Groq (「請幫工程部購買 2 台 MacBook Pro」 → `MacBook Pro × 2`,
routed to the same `NEEDS_APPROVAL` as the English case_002). Small models can
vary run-to-run on cross-lingual extraction, so for a reliability-critical live
demo, pin a larger model (`openai/gpt-oss-120b`) or a strong-multilingual one
(`meta-llama/llama-4-scout-17b-16e-instruct`) — both verified live against Groq
through the same unchanged call (just `PROCUREMENT_LLM_MODEL`). Either way the
deterministic core is language-agnostic: it sees only
`(category, amount, budget, bypass)`, never the raw text.

The safety properties hold regardless of planner: even an adversarial LLM output
cannot escalate privilege, because the decision and the approval gate are
deterministic.

## Docker

```bash
docker build -t procurement-agent .
docker run -p 8000:8000 procurement-agent
```

## Logs

Every run logs its full lifecycle to **stdout** — run start, each tool call
(including refusals), the final decision, and approval transitions — so
`docker logs <container>` shows exactly what the agent did and why:

```
... procurement.harness | run run_6ce8… START dept=engineering planner=rule_based msg='Please buy 2 MacBook Pro…'
... procurement.harness | run run_6ce8… tool check_policy: NEED_HUMAN_APPROVAL (policy_002) | category=hardware, amount=$5,000, budget=$20,000, bypass=False
... procurement.harness | run run_6ce8… DECISION=NEED_HUMAN_APPROVAL risk=MEDIUM rules=['policy_002'] -> status=NEEDS_APPROVAL
... procurement.harness | run run_6ce8… tool submit_to_erp: blocked: run not approved (state=NEEDS_APPROVAL)   # WARNING
```

Verbosity is `PROCUREMENT_LOG_LEVEL` (default `INFO`; `DEBUG` also logs the raw
planner intent). Gate refusals log at `WARNING`. To raise it in Docker:
`docker run -e PROCUREMENT_LOG_LEVEL=DEBUG -p 8000:8000 procurement-agent`.

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/agent/run` | Run a request → `{run_id, status, decision, tool_calls, draft_po}` |
| POST | `/agent/runs/{run_id}/approve` | Approve a `NEEDS_APPROVAL` run → submits to ERP |
| POST | `/agent/runs/{run_id}/reject` | Reject a `NEEDS_APPROVAL` run |
| GET  | `/health` | Liveness |

## Layout

```
app/
  main.py            FastAPI factory + planner selection
  api/routes.py      thin HTTP layer (no business logic)
  harness/           AgentHarness (loop, gate, trace) + run state machine
  planner/           rule_based (default) + llm, behind one interface
  policy/            deterministic engine + bypass detector
  tools/             lookup_catalog, check_policy, create_draft_po, submit_to_erp + registry
  schemas/           intent, decision, tools_io, output (pydantic)
  fixtures_loader.py the single point coupled to the fixture JSON shapes
fixtures/            catalog, policies, budgets, sample_requests
scripts/demo.py      end-to-end demonstration
tests/               case suite, gate, tool validation + registry dispatch, bypass (EN+ZH), logging, output schema, API
docs/                ARCHITECTURE.md, AI_USAGE.md
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the agent loop, tool
boundary, approval boundary, and schema-validation design.
