# Travel Agent

This directory contains the incremental implementation of the architecture in
[`TRAVEL_DESIGN.md`](TRAVEL_DESIGN.md). Phase 1 is a bounded planning vertical slice for a
five-day family trip under a fixed budget.

## Implemented

- strict Pydantic contracts for travelers, trip requests, offers, daily plans, and cost ledgers;
- deterministic `Decimal` budget verification that fails closed on missing or unknown costs;
- a small LangGraph workflow that searches, composes, and verifies a plan;
- replaceable inventory and model gateway protocols;
- fake, expiring inventory for reproducible local tests; and
- natural-language constraint extraction and optional plan explanation through local Ollama Qwen.

The fake inventory is not live or bookable. Daily activities are placeholders. This phase does not
include ReAct, MCP servers, databases, supplier adapters, payments, or booking.

## Design decisions

The language model does not calculate totals, select authoritative inventory, or decide whether a
plan satisfies the budget. Deterministic code owns those decisions. Ollama is isolated behind a
`ModelGateway` so a direct Hugging Face or cloud adapter can be added without changing the planner.

## Setup

Install project and development dependencies after generating the approved lock file:

```bash
uv sync --all-groups
```

Run the deterministic demonstration:

```bash
uv run travel-agent \
  --origin Chicago \
  --destination "Washington, DC" \
  --start-date 2026-10-05 \
  --budget 4000
```

The bundled fake offers total exactly USD 4,000 after the USD 200 contingency reserve.

## Command-line testing

Change to the project directory and activate the workspace environment:

```bash
cd /home/monster/Desktop/codes/AI-Agents/multi-step_autonomous_agent
source /home/monster/Desktop/codes/.venv/bin/activate
```

If `uv` is not available on the shell `PATH`, run the installed commands directly from the active
environment, such as `/home/monster/Desktop/codes/.venv/bin/travel-agent` and
`/home/monster/Desktop/codes/.venv/bin/pytest`.

### Check Ollama and Qwen

The default model is `qwen3.5:latest` at `http://localhost:11434`. Confirm Ollama is running and the
model is installed:

```bash
ollama list
curl --fail http://localhost:11434/api/tags
```

If the endpoint is unavailable, start Ollama in a separate terminal:

```bash
ollama serve
```

### Test deterministic flag input

This path does not call Qwen. It constructs a request from CLI flags and plans against fake,
expiring inventory:

```bash
travel-agent \
  --origin Chicago \
  --destination "Washington, DC" \
  --start-date 2026-10-05 \
  --budget 4000
```

### Test a complete natural-language request

This path asks the local Qwen model to extract constraints, validates them with Pydantic, and then
runs the deterministic planner:

```bash
travel-agent \
  --ollama-model qwen3.5:latest \
  --request "Plan a 5-day family trip from Chicago to Washington, DC starting \
2026-10-05 for travelers aged 38, 37, 10, and 7. Keep transport, lodging, local \
transport, activities, and meals within USD 4,000, including a USD 200 contingency. \
Prefer family-friendly activities and a moderate pace."
```

The demonstration inventory should produce five dates from `2026-10-05` through `2026-10-09` and
finish with:

```text
Budget accepted: True
Total: 4000 USD
Remaining: 0 USD
```

Qwen extracts candidate constraints using Ollama JSON mode and an exact-key contract. Pydantic is
the enforcement boundary before planning. This local Qwen build did not reliably obey Ollama's JSON
Schema grammar, so model output is never trusted based on generation settings alone. If dates, ages,
currency, included costs, or contingency are absent, the command prints clarification questions and
stops. It never silently fills those constraints.

### Test missing-information handling

Submit an incomplete request:

```bash
travel-agent \
  --ollama-model qwen3.5:latest \
  --request "Plan a five-day family trip from Chicago to Washington, DC under USD 4,000."
```

The command should ask for the missing start date, traveler ages, included cost categories, and
contingency instead of inventing them. Check the resulting status with:

```bash
echo $?
```

An exit code of `3` means clarification is required.

### Test Qwen explanation

Add `--use-ollama` to ask Qwen to explain the plan after deterministic verification:

```bash
travel-agent \
  --ollama-model qwen3.5:latest \
  --use-ollama \
  --request "Plan a 5-day family trip from Chicago to Washington, DC starting \
2026-10-05 for travelers aged 38, 37, 10, and 7. Keep transport, lodging, local \
transport, activities, and meals within USD 4,000, including a USD 200 contingency."
```

Qwen cannot change the plan, totals, or verification status.

### CLI exit codes

| Code | Meaning |
|---|---|
| `0` | A budget-verified plan was produced |
| `2` | The candidate plan failed deterministic budget verification |
| `3` | Required trip information is missing |
| `4` | Ollama connection, timeout, or model-output validation failed |

## Validation

Run the complete automated test suite:

```bash
uv run pytest
uv run ruff check .
uv run pyright --pythonpath /home/monster/Desktop/codes/.venv/bin/python
```

Equivalent commands that do not depend on `uv` being on the shell `PATH` are:

```bash
/home/monster/Desktop/codes/.venv/bin/pytest tests
/home/monster/Desktop/codes/.venv/bin/ruff check .
/home/monster/Desktop/codes/.venv/bin/pyright \
  --pythonpath /home/monster/Desktop/codes/.venv/bin/python
```

## Current limitations

This repository currently implements a tested planning vertical slice, not a production travel
platform:

- inventory is generated by `FakeInventory`; prices, availability, and expiration windows do not
  come from airlines, hotels, aggregators, or other live suppliers;
- the package composer selects the cheapest offer in each required category rather than optimizing
  combinations across schedules, geography, occupancy, cancellation terms, and preferences;
- daily activities are placeholders without opening hours, travel times, reservations, or age and
  accessibility checks;
- natural-language extraction depends on local Qwen behavior; Ollama JSON mode and exact-key
  prompting improve consistency, but Pydantic validation remains the actual trust boundary;
- clarification is stateless: the CLI prints missing questions and exits instead of preserving a
  conversation and merging follow-up answers;
- there is no bounded ReAct search loop or MCP client/server implementation yet;
- there is no RAG layer for destination content, policies, or cited travel guidance;
- runs, plans, offers, and audit events are not persisted to PostgreSQL or another durable store;
- there is no FastAPI service, authentication, tenant isolation, queue, telemetry pipeline, or web
  interface;
- quote revalidation, holds, booking, payment, ticketing, cancellation, exchange, refund, and
  disruption workflows are design-only and must not be inferred from the demonstration output; and
- the shared workspace virtual environment can create dependency coupling with unrelated projects;
  a dedicated project environment is recommended before expanding the dependency surface.

Do not use the current implementation with production supplier, payment, traveler-identity, or
booking credentials. Generated plans are indicative demonstrations and are not bookable.

## Recommended next phase

Phase 2 should implement a **multi-supplier search vertical slice through MCP**, using simulated
suppliers before connecting any commercial API.

The phase should add:

1. a travel-search MCP server exposing canonical air, lodging, local-transport, and activity search
   tools;
2. separate fake supplier adapters with deterministic fixtures, latency, quotas, throttling, stale
   offers, malformed responses, and outage modes;
3. an MCP client in the agent worker with a reviewed tool allowlist, input/output validation,
   deadlines, output limits, and trace context;
4. canonical offer normalization, supplier provenance, observation timestamps, expiration, and
   deduplication;
5. bounded parallel fan-out with per-supplier concurrency and rate limits;
6. partial-result behavior when one supplier is unavailable, without presenting missing coverage as
   complete;
7. package composition over normalized candidates while retaining deterministic budget checks; and
8. contract and integration tests for success, timeout, throttling, malformed output, stale offers,
   and supplier failure.

This phase is recommended before adding ReAct because adaptive reasoning is useful only after the
agent has multiple meaningful, policy-controlled tools. It is recommended before a real supplier
API because the MCP boundary, canonical contracts, quotas, and failure semantics can first be proven
without credentials or commercial certification.

Phase 2 is complete when the CLI can submit one validated request, query at least three simulated
suppliers through MCP, return normalized and source-attributed partial or complete results, build a
budget-verified five-day plan, and pass deterministic failure-mode tests.

After Phase 2, the recommended order is:

1. add the bounded ReAct search and replanning loop;
2. add FastAPI, durable checkpoints, PostgreSQL, and audit events;
3. add stable-content and policy RAG with provenance;
4. integrate one supplier certification environment and authoritative quote revalidation; and
5. implement approval-gated booking only after idempotency, reconciliation, and operations support
   are proven.