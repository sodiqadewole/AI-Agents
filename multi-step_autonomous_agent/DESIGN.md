# Multi-Step Autonomous Agent Design

## Document status

| Field | Value |
|---|---|
| Status | Proposed |
| Audience | Application engineers, platform engineers, security reviewers, and operators |
| Initial implementation | Python 3.12, LangGraph, FastAPI, PostgreSQL, Redis, and object storage |
| Deployment targets | Local Docker Compose, Microsoft Azure, and Amazon Web Services |

## 1. Purpose

This document defines a production-oriented system for an autonomous agent that can:

- translate a user goal into a dependency-aware plan;
- execute multiple bounded steps through validated tools;
- persist working, episodic, semantic, and procedural memory;
- delegate independent work to specialist agents;
- verify outputs against explicit acceptance criteria;
- pause for human approval before sensitive operations;
- recover from process restarts without losing workflow state; and
- run consistently on a developer machine, Azure, or AWS.

The system is a stateful workflow whose decisions may be proposed by a language model but whose permissions, budgets, state transitions, retries, and termination are enforced by application code.

## 2. Goals and non-goals

### 2.1 Goals

1. **Durable execution:** checkpoint after every state transition and resume interrupted runs.
2. **Controlled autonomy:** enforce iteration, token, time, cost, and tool-call budgets.
3. **Safe tool use:** validate all arguments and isolate tools with side effects.
4. **Useful memory:** retrieve scoped evidence and retain only reviewed, attributable facts.
5. **Measured collaboration:** use specialist agents where isolation or parallelism improves results.
6. **Verifiable completion:** require evidence that task-specific acceptance criteria passed.
7. **Portable deployment:** keep domain contracts independent of model and cloud providers.
8. **Operational visibility:** trace model calls, tool calls, state transitions, costs, and failures.

### 2.2 Non-goals

- Unbounded self-improvement or self-modifying production code.
- Allowing language models to bypass authorization or approval policies.
- Treating model-generated statements as trusted long-term memory.
- Supporting arbitrary host-level shell access in the control-plane service.
- Creating many conversational agents when one workflow step would suffice.

## 3. Requirements

### 3.1 Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | Accept a goal, caller identity, tenant or project scope, budget, and optional deadline. |
| FR-2 | Produce a structured plan containing dependencies, tools, assignees, and acceptance criteria. |
| FR-3 | Schedule ready steps and run independent read-only steps concurrently. |
| FR-4 | Validate tool requests with typed schemas and policy checks. |
| FR-5 | Record observations, artifacts, provenance, and step outcomes. |
| FR-6 | Retrieve relevant memory with scope, recency, and authorization filters. |
| FR-7 | Delegate tasks to planner, researcher, executor, verifier, and memory-manager roles. |
| FR-8 | Replan only after material new evidence, a failed dependency, or an explicit request. |
| FR-9 | Require human approval for configured high-risk operations. |
| FR-10 | Resume a run from its latest durable checkpoint. |
| FR-11 | Stream progress events and expose final artifacts through an API. |
| FR-12 | Cancel a run and prevent new work from being scheduled. |

### 3.2 Non-functional requirements

| Area | Initial target |
|---|---|
| API availability | 99.9% monthly for the managed control plane |
| State durability | No acknowledged transition lost after checkpoint success |
| API latency | Under 500 ms p95 excluding model and tool execution |
| Recovery point objective | 15 minutes for regional data loss |
| Recovery time objective | 4 hours for regional restoration |
| Isolation | Tenant-scoped data access and per-tool credentials |
| Auditability | Immutable record of actor, prompt version, tool request, decision, and outcome |
| Portability | No cloud SDK calls inside core workflow or domain modules |

## 4. Architecture

```mermaid
flowchart LR
    Client[CLI or application] --> API[FastAPI control plane]
    API --> Auth[Identity and policy]
    API --> Orchestrator[Durable orchestrator]
    Orchestrator --> Planner[Planner]
    Orchestrator --> Queue[Task queue]
    Queue --> Workers[Specialist workers]
    Workers --> Router[Tool router]
    Router --> Sandbox[Sandboxed tools]
    Router --> APIs[Approved external APIs]
    Workers --> Models[Model gateway]
    Orchestrator --> Verifier[Verifier]
    Orchestrator <--> State[(PostgreSQL)]
    Workers <--> Cache[(Redis)]
    Workers <--> Objects[(Artifact storage)]
    Workers <--> Memory[Memory service]
    Memory <--> State
    API --> Events[Event stream]
    Orchestrator --> Telemetry[OpenTelemetry]
    Workers --> Telemetry
```

### 4.1 Components

**API control plane**

- Authenticates callers and authorizes access to runs and artifacts.
- Creates, reads, cancels, and resumes runs.
- Streams server-sent events or WebSocket progress messages.
- Never executes arbitrary user code directly.

**Durable orchestrator**

- Owns the run state machine and step dependency graph.
- Applies budgets, retries, approval gates, and termination rules.
- Uses LangGraph checkpoints for the first implementation.
- Can later be placed behind Temporal without changing domain contracts.

**Model gateway**

- Presents one internal interface for Azure OpenAI, Amazon Bedrock, OpenAI-compatible local models, and test doubles.
- Enforces timeouts, retry policy, token limits, structured-output validation, and usage accounting.
- Records model name and prompt-template version, but redacts secrets and configured sensitive values.

**Task queue and workers**

- Decouple long-running steps from API instances.
- Claim tasks with leases, heartbeat while running, and make completion idempotent.
- Separate worker pools by tool permissions and risk class.

**Tool router**

- Resolves a tool name to a versioned implementation.
- Validates input and output schemas.
- Checks caller scope, run policy, network policy, and approval state.
- Generates an idempotency key from run, step, attempt, and tool-call identifiers.

**Memory service**

- Retrieves scoped memories before planning and execution.
- Ranks by semantic similarity, metadata match, recency, confidence, and source quality.
- Consolidates successful run outcomes asynchronously.

**Verifier**

- Evaluates acceptance criteria using tests, schemas, source evidence, or domain checks.
- Cannot approve its own tool side effects.
- Returns structured pass, fail, or inconclusive results with evidence.

### 4.2 Recommended source layout

```text
multi-step_autonomous_agent/
├── DESIGN.md
├── pyproject.toml
├── Dockerfile
├── compose.yaml
├── .env.example
├── alembic.ini
├── migrations/
├── src/autonomous_agent/
│   ├── api/
│   ├── domain/
│   ├── orchestration/
│   ├── agents/
│   ├── tools/
│   ├── memory/
│   ├── models/
│   ├── persistence/
│   ├── policy/
│   └── telemetry/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── evaluations/
└── infra/
    ├── azure/
    └── aws/
```

## 5. Agent lifecycle

### 5.1 State machine

```mermaid
stateDiagram-v2
    [*] --> Planning
    Planning --> Executing: valid plan
    Executing --> WaitingForApproval: sensitive action
    WaitingForApproval --> Executing: approved
    WaitingForApproval --> Cancelled: rejected or expired
    Executing --> Verifying: candidate result
    Verifying --> Executing: local correction
    Verifying --> Planning: material evidence requires replan
    Verifying --> Completed: criteria satisfied
    Planning --> Failed: invalid plan or budget exceeded
    Executing --> Failed: unrecoverable failure
    Verifying --> Failed: retry or budget exhausted
    Planning --> Cancelled: cancellation requested
    Executing --> Cancelled: cancellation requested
    Completed --> [*]
    Failed --> [*]
    Cancelled --> [*]
```

Every transition runs in a transaction that writes the new state and an outbox event. A queue publisher forwards committed outbox events. This prevents a checkpoint from being committed while the corresponding work notification is lost.

### 5.2 Run and plan contracts

```python
from typing import Any, Literal

from pydantic import BaseModel, Field


class AcceptanceCriterion(BaseModel):
    description: str
    verification_method: Literal["test", "schema", "source", "human", "custom"]


class PlanStep(BaseModel):
    id: str
    description: str
    assigned_role: str
    allowed_tools: list[str]
    dependencies: list[str] = Field(default_factory=list)
    criteria: list[AcceptanceCriterion]
    status: Literal["pending", "ready", "running", "blocked", "done", "failed"] = "pending"


class RunState(BaseModel):
    run_id: str
    tenant_id: str
    goal: str
    plan: list[PlanStep] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    iteration: int = 0
    token_budget_remaining: int
    cost_budget_remaining_usd: float
    deadline_epoch_seconds: int | None = None
    status: Literal[
        "planning",
        "executing",
        "waiting_for_approval",
        "verifying",
        "completed",
        "failed",
        "cancelled",
    ] = "planning"
```

### 5.3 Bounded orchestration loop

The orchestrator, not the model, selects valid state transitions:

```python
async def run_until_yield(state: RunState) -> RunState:
    while state.status not in {"completed", "failed", "cancelled"}:
        enforce_run_budget(state)
        await check_cancellation(state.run_id)

        if state.status == "planning":
            state = await create_or_revise_plan(state)
        elif state.status == "executing":
            state = await dispatch_ready_steps(state)
        elif state.status == "verifying":
            state = await verify_candidate_result(state)
        elif state.status == "waiting_for_approval":
            return state

        state.iteration += 1
        await checkpoint_and_publish(state)

    return state
```

Initial defaults are 20 orchestration iterations, 50,000 tokens, 30 minutes, and a caller-selected cost ceiling. Limits are configuration values and may only be raised within the caller's policy.

## 6. Planning and multi-agent collaboration

### 6.1 Roles

| Role | Responsibility | Default tool access |
|---|---|---|
| Planner | Decompose goals and revise invalidated plans | Memory retrieval only |
| Researcher | Gather and compare evidence | Read-only search and retrieval |
| Executor | Produce artifacts and invoke domain tools | Task-specific allowlist |
| Verifier | Check acceptance criteria independently | Read-only checks and test runners |
| Memory manager | Retrieve, summarize, and propose durable memories | Memory APIs only |
| Supervisor | Apply policy and choose workflow transitions | No direct external tools |

These are logical roles. They do not require separate services or different models. Begin with one worker service and route role-specific prompts through it; split worker pools only for scaling or security isolation.

### 6.2 Delegation contract

```python
class TaskPacket(BaseModel):
    task_id: str
    run_id: str
    tenant_id: str
    objective: str
    context_refs: list[str]
    acceptance_criteria: list[AcceptanceCriterion]
    allowed_tools: list[str]
    output_schema: dict[str, Any]
    token_budget: int
    deadline_epoch_seconds: int
```

A worker returns a structured result containing status, artifact references, evidence references, confidence, unresolved issues, token usage, cost, and retriable error information. Agents do not exchange open-ended chat messages. The supervisor communicates through task packets and persisted results.

### 6.3 Concurrency rules

- Dispatch a step only when all dependencies are complete.
- Parallelize independent read-only work by default.
- Serialize steps that mutate the same resource.
- Use resource locks with expiration for external mutations.
- Cap fan-out per run and globally to protect model and API quotas.
- Cancel downstream work when a required dependency permanently fails.
- Deduplicate worker completion by task ID and attempt number.

## 7. Tool system

### 7.1 Tool contract

Each registered tool declares:

- unique name and semantic version;
- Pydantic input and output models;
- read-only or mutating behavior;
- risk class: low, medium, high, or prohibited;
- timeout and maximum output size;
- allowed network destinations and filesystem roots;
- retry and idempotency behavior;
- credential scope; and
- approval requirement.

### 7.2 Execution policy

1. Parse model output as structured data; never execute text directly.
2. Confirm the tool is in the task packet's allowlist.
3. Validate arguments and normalize resource identifiers.
4. Evaluate policy and approval requirements.
5. Execute in the appropriate worker pool or sandbox.
6. Validate and truncate the result before returning it to a model.
7. Store full permitted output as an artifact and a digest in the observation.
8. Record latency, result status, actor, and provenance.

Web pages, documents, repository content, and tool output are untrusted data. Instructions found inside them must not change system policy, tool permissions, or the current task.

### 7.3 Code execution

Do not mount the Docker socket or host home directory into an execution container. Run code with:

- a read-only base filesystem;
- a temporary writable workspace;
- non-root user and dropped Linux capabilities;
- CPU, memory, process, and wall-time limits;
- outbound network disabled unless explicitly required;
- an artifact upload channel rather than shared cloud credentials; and
- image allowlisting and vulnerability scanning.

Use gVisor, Kata Containers, Azure Container Apps Jobs, AWS Fargate tasks, or another hardened boundary for workloads that execute generated code.

## 8. Memory design

| Layer | Contents | Storage | Retention |
|---|---|---|---|
| Working | Current plan, selected evidence, intermediate values | PostgreSQL checkpoint | Run lifetime plus audit window |
| Episodic | Actions and outcomes from previous runs | PostgreSQL | Policy-defined, such as 90 days |
| Semantic | Stable facts and summaries with embeddings | PostgreSQL with pgvector | Until invalidated or expired |
| Procedural | Versioned prompts, policies, and approved strategies | Git plus PostgreSQL metadata | Indefinite versions |
| Artifact | Reports, datasets, logs, and generated files | Blob storage or S3 | Lifecycle policy |

### 8.1 Memory record

Every durable memory contains:

- tenant and optional user/project scope;
- normalized fact or summary;
- source artifact and source segment references;
- creation and last-confirmed timestamps;
- confidence and sensitivity labels;
- embedding model and version;
- expiration or review date; and
- superseded-by reference when corrected.

### 8.2 Retrieval

1. Enforce tenant, user, project, and sensitivity filters before similarity search.
2. Retrieve lexical and vector candidates.
3. Rerank by relevance, source quality, recency, and confidence.
4. Return small excerpts and references within a token budget.
5. Tell the model when evidence conflicts or is stale.

### 8.3 Consolidation

The memory manager proposes memories only after a completed or explicitly reviewed run. Deterministic checks reject secrets, raw prompt-injection content, unsupported claims, and duplicates. High-impact facts require human review or corroborating evidence. Users must be able to inspect and delete memories within their scope.

## 9. Persistence model

The initial PostgreSQL schema contains:

| Table | Purpose |
|---|---|
| `runs` | Goal, status, owner, policy, budgets, and timestamps |
| `checkpoints` | Serialized workflow state with monotonic version |
| `plan_steps` | Dependency graph, assignee, criteria, and step status |
| `tasks` | Worker lease, attempt, heartbeat, and completion data |
| `tool_calls` | Validated request digest, result, timing, and audit fields |
| `approvals` | Requested action, approver, decision, expiry, and reason |
| `artifacts` | URI, content type, checksum, tenant, and retention metadata |
| `memories` | Scoped text, embedding, provenance, confidence, and expiry |
| `usage_events` | Tokens, model, tool cost, and billable dimensions |
| `outbox_events` | Transactional events awaiting publication |

Use row-level security where practical, always include `tenant_id` in unique keys and queries, encrypt storage, and use Alembic for forward-only migrations. Artifact rows hold object URIs and checksums, not large binary payloads.

## 10. API surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/runs` | Create a run and return its ID |
| `GET` | `/v1/runs/{run_id}` | Read status, plan, budgets, and result |
| `POST` | `/v1/runs/{run_id}/cancel` | Request cancellation |
| `POST` | `/v1/runs/{run_id}/resume` | Resume a recoverable or approved run |
| `GET` | `/v1/runs/{run_id}/events` | Stream progress events |
| `POST` | `/v1/approvals/{approval_id}` | Approve or reject a gated action |
| `GET` | `/v1/artifacts/{artifact_id}` | Return metadata and a short-lived download URL |
| `GET` | `/health/live` | Process liveness |
| `GET` | `/health/ready` | Database, queue, and configuration readiness |

All mutating requests accept an `Idempotency-Key`. Do not return chain-of-thought or hidden model reasoning. Expose plans, actions, evidence, concise decision summaries, and policy outcomes instead.

## 11. Security and governance

### 11.1 Identity and authorization

- Use OpenID Connect for users and workload identity for services.
- Map identities to tenant/project roles at the API boundary.
- Issue separate identities to API, orchestrator, read-only workers, mutating workers, and migration jobs.
- Prefer managed identity or IAM roles over static cloud credentials.
- Generate short-lived artifact URLs after authorization.

### 11.2 Approval policy

Human approval is required by default for:

- deletion or irreversible updates;
- purchases, payments, or paid resource creation;
- outbound messages sent as a user or organization;
- production deployment or infrastructure mutation;
- access to newly requested sensitive data; and
- increasing a run beyond configured cost limits.

Approval records bind the exact normalized action and arguments. Changing the arguments invalidates the approval.

### 11.3 Secret and data handling

- Store local secrets in an ignored `.env`; use Key Vault or Secrets Manager in cloud environments.
- Redact secrets before prompts, logs, traces, and durable observations.
- Classify data before selecting a model endpoint or region.
- Disable provider training and retention where required by organizational policy.
- Encrypt in transit and at rest, and rotate credentials without rebuilding images.
- Define deletion workflows covering database records, embeddings, caches, and artifacts.

### 11.4 Supply chain

- Pin direct dependencies and commit lock files.
- Build minimal non-root images with a fixed base-image digest.
- Generate a software bill of materials and scan dependencies and images.
- Sign images and admit only trusted signatures in production.
- Keep development tools out of runtime images.

## 12. Reliability and failure handling

- Use exponential backoff with jitter only for classified transient failures.
- Do not retry validation, authorization, or policy failures.
- Respect model-provider `Retry-After` headers and maintain per-provider circuit breakers.
- Heartbeat long-running tasks and reclaim expired leases.
- Place exhausted asynchronous tasks in a dead-letter queue.
- Make every side-effecting tool idempotent or require a reconciliation operation.
- Reconcile unknown outcomes before retrying a timed-out mutation.
- Save a checkpoint before requesting approval and after recording its decision.
- Degrade to read-only operation when mutation workers or approval services are unavailable.

## 13. Observability and evaluation

### 13.1 Telemetry

Instrument the API, orchestrator, workers, model gateway, queue, database, and tools with OpenTelemetry. Correlate records using `trace_id`, `run_id`, `task_id`, and `tool_call_id`.

Track at minimum:

- active, completed, failed, cancelled, and approval-blocked runs;
- end-to-end and per-step latency;
- model latency, tokens, cost, retries, and throttling;
- tool success, error class, timeout, and policy-denial rates;
- queue depth, oldest message age, lease expiry, and dead letters;
- checkpoint and memory retrieval latency;
- verifier pass, fail, and inconclusive rates; and
- plan revisions, repeated actions, and budget exhaustion.

Do not export raw prompts, tool output, or memory text by default. Use sampled, redacted debugging with access controls and an expiry.

### 13.2 Evaluation gates

Maintain a versioned suite of representative tasks with expected artifacts and deterministic checks. Before promoting a prompt, model, tool, or policy version, compare:

- task success and verifier agreement;
- unsafe or unauthorized action rate;
- unsupported-claim rate;
- mean cost and p95 latency;
- tool-call efficiency and repeated-action rate; and
- memory precision, recall, and cross-tenant isolation.

Run unit tests on every change, integration tests against disposable dependencies, offline evaluations before merge, and a small production canary before full rollout.

## 14. Local deployment

### 14.1 Prerequisites

- Linux, macOS, or Windows with WSL2
- Git
- Docker Engine with the Compose v2 plugin
- 8 GB RAM minimum; 16 GB recommended
- A model-provider API key, or a local OpenAI-compatible endpoint such as Ollama
- Optional Python 3.12 and `uv` for development outside containers

### 14.2 Local topology

Docker Compose should run:

- `api`: FastAPI control plane on port `8000`;
- `worker`: planner, executor, verifier, and memory roles;
- `postgres`: PostgreSQL with pgvector;
- `redis`: task queue, leases, and short-lived cache;
- `minio`: S3-compatible artifact storage; and
- optional `otel-collector` plus Jaeger or Grafana for development telemetry.

Use named volumes for PostgreSQL and MinIO. Mount source code only in the development override. The production-like compose profile must run the same immutable image used for API and workers.

### 14.3 Environment configuration

Create `.env` from a committed `.env.example` and set values equivalent to:

```dotenv
APP_ENV=local
DATABASE_URL=postgresql+psycopg://agent:change-me@postgres:5432/agent
REDIS_URL=redis://redis:6379/0
ARTIFACT_ENDPOINT=http://minio:9000
ARTIFACT_BUCKET=agent-artifacts
ARTIFACT_ACCESS_KEY=minioadmin
ARTIFACT_SECRET_KEY=change-me
MODEL_PROVIDER=openai
MODEL_NAME=your-model-deployment
OPENAI_API_KEY=replace-locally
MAX_RUN_ITERATIONS=20
DEFAULT_TOKEN_BUDGET=50000
DEFAULT_COST_BUDGET_USD=5.00
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

For Ollama, configure the model gateway's OpenAI-compatible base URL as `http://host.docker.internal:11434/v1`. On Linux, add `host-gateway` mapping in Compose. Keep `.env`, database data, generated artifacts, and telemetry data out of Git.

### 14.4 Runbook

After the implementation files described by this design exist:

```bash
cd AI-Agents/multi-step_autonomous_agent
docker compose build
docker compose up -d postgres redis minio
docker compose run --rm api alembic upgrade head
docker compose up -d api worker
docker compose ps
curl --fail http://localhost:8000/health/ready
```

Submit a smoke-test run:

```bash
curl --request POST http://localhost:8000/v1/runs \
  --header 'Content-Type: application/json' \
  --header 'Idempotency-Key: local-smoke-1' \
  --data '{"goal":"Summarize the supplied documents","token_budget":5000,"cost_budget_usd":1.0}'
```

Inspect logs with `docker compose logs -f api worker`. Stop services with `docker compose down`; add `--volumes` only when intentionally deleting local state.

### 14.5 Local development without containers

Run PostgreSQL, Redis, and MinIO in Compose, then start API and worker processes from the virtual environment:

```bash
uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn autonomous_agent.api.main:app --reload --port 8000
uv run python -m autonomous_agent.workers.main
```

Use a separate test database. Integration tests must never point to a developer or production database.

## 15. Azure deployment

### 15.1 Recommended service mapping

| Capability | Azure service |
|---|---|
| Container images | Azure Container Registry |
| API and orchestrator | Azure Container Apps |
| Long-running isolated tools | Azure Container Apps Jobs |
| Queue | Azure Service Bus Premium |
| Relational and vector data | Azure Database for PostgreSQL Flexible Server with `vector` extension |
| Cache and leases | Azure Managed Redis |
| Artifacts | Azure Blob Storage |
| Models | Azure OpenAI Service, with model gateway abstraction |
| Secrets and keys | Azure Key Vault |
| Identity | Microsoft Entra ID and managed identities |
| Telemetry | Azure Monitor, Application Insights, and Log Analytics |
| DNS and edge protection | Azure Front Door with Web Application Firewall, when internet-facing |

Azure product availability and model names vary by region and subscription. Confirm current regional availability, quotas, private-network support, and pricing before selecting the production region.

### 15.2 Azure network and identity

1. Create a virtual network with subnets for Container Apps infrastructure and private endpoints.
2. Disable public access to PostgreSQL, Blob Storage, Redis, Service Bus, Key Vault, and model endpoints where supported.
3. Use private DNS zones linked to the virtual network.
4. Give each Container App or Job a user-assigned managed identity.
5. Grant identities only the required data-plane roles, such as Blob Data Contributor for artifact workers and Key Vault Secrets User for services that resolve secrets.
6. Put Front Door and WAF in front of an external API, or make the Container Apps environment internal for private workloads.

### 15.3 Azure provisioning

Define all resources using Bicep or Terraform under `infra/azure`. Separate reusable modules from environment parameter files. A production deployment should provision:

- resource group and regional naming tags;
- Log Analytics workspace and Application Insights;
- virtual network, subnets, private endpoints, and private DNS;
- Container Apps environment, API app, worker apps, and sandbox job;
- Container Registry with image scanning and retention;
- PostgreSQL Flexible Server with zone redundancy, backups, and pgvector enabled;
- Service Bus namespace, queues, dead-lettering, and duplicate detection;
- Azure Managed Redis;
- storage account and private artifact container;
- Key Vault with soft delete and purge protection;
- Azure OpenAI resource and deployment, if used; and
- alerts, dashboards, budgets, and diagnostic settings.

Illustrative deployment flow:

```bash
az login
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
az group create --name "$AZURE_RESOURCE_GROUP" --location "$AZURE_LOCATION"
az deployment group what-if \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --template-file infra/azure/main.bicep \
  --parameters environment=dev
az deployment group create \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --template-file infra/azure/main.bicep \
  --parameters environment=dev
```

Build and publish the immutable image:

```bash
az acr login --name "$AZURE_CONTAINER_REGISTRY"
docker build --tag "$AZURE_CONTAINER_REGISTRY.azurecr.io/autonomous-agent:$GIT_SHA" .
docker push "$AZURE_CONTAINER_REGISTRY.azurecr.io/autonomous-agent:$GIT_SHA"
```

Prefer CI workload-identity federation to `az login` with a stored service-principal secret. Inject non-secret settings as Container App environment variables and secret references through Key Vault. Use managed identity for Azure resources instead of storage keys or database passwords where supported.

### 15.4 Azure application configuration

Set provider-neutral application variables plus Azure-specific references:

```dotenv
APP_ENV=production
MODEL_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-approved-deployment
QUEUE_PROVIDER=azure_service_bus
ARTIFACT_PROVIDER=azure_blob
OTEL_SERVICE_NAME=autonomous-agent
```

Resolve database, queue, cache, and endpoint details from deployment outputs or a configuration service. Keep secret values in Key Vault. Validate that the selected Azure OpenAI deployment supports required structured output and content-policy behavior.

### 15.5 Azure release procedure

1. Run tests, security scans, and offline agent evaluations.
2. Build once and sign the image.
3. Apply infrastructure `what-if`, obtain approval, then deploy changes.
4. Run database migrations as a one-off Container Apps Job using a migration identity.
5. Deploy a new API and worker revision with zero initial traffic.
6. Run readiness and synthetic end-to-end tests.
7. Shift 5%, 25%, then 100% of API traffic while monitoring errors, cost, and verifier outcomes.
8. Drain old workers after their task leases complete.
9. Roll back traffic to the previous revision if service-level or evaluation thresholds fail. Do not automatically reverse a database migration; use a compatible forward fix.

### 15.6 Azure scaling and recovery

- Scale API replicas from HTTP concurrency and workers from Service Bus queue depth using KEDA integration.
- Set a non-zero minimum for production API and supervisor workloads.
- Bound maximum replicas to protect model, PostgreSQL, and Service Bus quotas.
- Enable PostgreSQL zone redundancy and point-in-time restore.
- Use geo-redundant artifact replication if the recovery objective requires it.
- Export infrastructure definitions and test restoration into a separate resource group at least quarterly.
- For multi-region operation, use one write region initially; active-active orchestration requires explicit run ownership and conflict handling.

## 16. AWS deployment

### 16.1 Recommended service mapping

| Capability | AWS service |
|---|---|
| Container images | Amazon Elastic Container Registry |
| API and orchestrator | Amazon ECS on AWS Fargate |
| Long-running isolated tools | One-off ECS Fargate tasks |
| Queue | Amazon Simple Queue Service with dead-letter queues |
| Relational and vector data | Amazon RDS for PostgreSQL or Aurora PostgreSQL with pgvector |
| Cache and leases | Amazon ElastiCache for Redis-compatible engines |
| Artifacts | Amazon S3 |
| Models | Amazon Bedrock, with model gateway abstraction |
| Secrets and keys | AWS Secrets Manager and AWS Key Management Service |
| Identity | AWS IAM roles for tasks and IAM Identity Center for operators |
| Telemetry | Amazon CloudWatch, AWS X-Ray, and AWS Distro for OpenTelemetry |
| DNS and edge protection | Route 53, Application Load Balancer, AWS WAF, and optionally CloudFront |

Bedrock models, features, quotas, and cross-region inference options vary by region. Confirm model access, data residency, interface endpoint support, and pricing before selecting a region.

### 16.2 AWS network and identity

1. Use at least two Availability Zones.
2. Place the Application Load Balancer in public subnets only when an internet-facing API is needed.
3. Place ECS tasks, RDS, and ElastiCache in private subnets without public IP addresses.
4. Add VPC endpoints for ECR, S3, SQS, Secrets Manager, CloudWatch, and Bedrock where available to minimize public egress.
5. Use separate ECS task roles for API, orchestrator, read-only workers, mutating workers, and migration tasks.
6. Restrict IAM actions and resources; use condition keys for bucket prefixes, queues, model IDs, source VPC endpoints, and regions.
7. Use security groups that permit only required service-to-service paths.

### 16.3 AWS provisioning

Define resources with AWS CDK or Terraform under `infra/aws`. A production stack should include:

- VPC, public/private subnets, NAT or controlled egress, and VPC endpoints;
- ECR repositories with enhanced scanning and lifecycle policies;
- ECS cluster, task definitions, API service, worker services, and sandbox task definition;
- Application Load Balancer, TLS listener, Route 53 record, and WAF rules;
- RDS or Aurora PostgreSQL with Multi-AZ, encryption, backups, and pgvector;
- ElastiCache replication group;
- SQS task queues with dead-letter queues, redrive policy, and long polling;
- versioned and encrypted S3 artifact bucket with lifecycle rules;
- Secrets Manager entries and KMS keys;
- CloudWatch log groups, alarms, dashboards, and ADOT collectors; and
- AWS Budgets and cost-allocation tags.

Illustrative CDK deployment flow:

```bash
aws sso login --profile agent-dev
export AWS_PROFILE=agent-dev
export AWS_REGION=us-east-1
cd infra/aws
npm ci
npx cdk synth
npx cdk diff AgentDevStack
npx cdk deploy AgentDevStack --require-approval broadening
```

Build and publish the image:

```bash
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
docker build --tag autonomous-agent:$GIT_SHA .
docker tag autonomous-agent:$GIT_SHA \
  "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/autonomous-agent:$GIT_SHA"
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/autonomous-agent:$GIT_SHA"
```

CI should use GitHub Actions or another CI system with OpenID Connect federation to an IAM role. Do not create long-lived IAM access keys for deployments.

### 16.4 AWS application configuration

```dotenv
APP_ENV=production
MODEL_PROVIDER=bedrock
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=your-approved-model-id
QUEUE_PROVIDER=sqs
ARTIFACT_PROVIDER=s3
ARTIFACT_BUCKET=your-private-agent-artifact-bucket
OTEL_SERVICE_NAME=autonomous-agent
```

Use the ECS task role for Bedrock, SQS, S3, KMS, and telemetry. Resolve database and cache credentials from Secrets Manager at startup or through an approved sidecar. Never place secret values in task-definition plaintext environment variables.

### 16.5 AWS release procedure

1. Run tests, scans, and offline evaluations.
2. Build once, scan, sign, and push the image to ECR.
3. Review the CDK or Terraform change set and deploy approved infrastructure changes.
4. Run migrations as a one-off ECS task with a dedicated task role.
5. Register immutable task definitions using the image digest.
6. Deploy ECS services with circuit-breaker rollback and minimum healthy capacity.
7. Run synthetic API and complete-run tests through the load balancer.
8. Use weighted target groups or CodeDeploy blue/green deployment for production canaries.
9. Drain old workers after in-flight leases complete and monitor dead-letter queues.

### 16.6 AWS scaling and recovery

- Scale API tasks on request count or CPU and workers on SQS visible-message count and oldest-message age.
- Keep minimum API and supervisor capacity across at least two Availability Zones.
- Cap task counts to stay within Bedrock, RDS, NAT, and account quotas.
- Enable RDS Multi-AZ, automated backups, and point-in-time recovery.
- Enable S3 versioning and, when required, cross-region replication.
- Copy database snapshots to a recovery region and test restore procedures quarterly.
- Route new runs away from an impaired region; resume checkpointed runs only after run ownership is safely transferred.

## 17. Cross-cloud portability

Core code depends on internal ports rather than provider SDKs:

```python
class ModelGateway(Protocol): ...
class TaskQueue(Protocol): ...
class ArtifactStore(Protocol): ...
class CheckpointStore(Protocol): ...
class SecretResolver(Protocol): ...
class TelemetrySink(Protocol): ...
```

Provider adapters live under infrastructure-facing modules. Contract tests run against every adapter. The local stack uses PostgreSQL, Redis, MinIO, and a configurable model endpoint; Azure and AWS adapters preserve the same task, artifact, and checkpoint semantics.

Avoid claiming transparent failover between Azure and AWS model providers. Models differ in tool calling, structured output, safety behavior, token accounting, and quality. Qualify each model/provider combination with the evaluation suite before enabling it.

## 18. CI/CD pipeline

The pipeline should:

1. format, lint, type-check, and run unit tests;
2. run integration tests with ephemeral PostgreSQL, Redis, and object storage;
3. run prompt-injection, authorization, and tenant-isolation tests;
4. run offline agent evaluations and compare to the accepted baseline;
5. scan dependencies, secrets, infrastructure code, and container images;
6. generate an SBOM, sign the image, and publish by commit SHA;
7. preview infrastructure changes and require production approval;
8. migrate using a dedicated job;
9. canary API and workers; and
10. record deployed image, prompts, model configuration, migrations, and policy versions.

Promotion uses the same image digest from development through production. Environment differences are configuration and managed resource bindings, not rebuilt source.

## 19. Cost controls

- Require per-run token and dollar budgets.
- Enforce global and tenant-specific concurrency and daily spend limits.
- Route simple classification and summarization to qualified lower-cost models.
- Cache deterministic, tenant-safe model and retrieval results where policy permits.
- Limit retrieved context and summarize observations before they overflow the working context.
- Store large tool results as artifacts rather than repeatedly placing them in prompts.
- Scale workers to zero in non-production environments when acceptable.
- Alert on spend rate, not only monthly totals.
- Tag cloud resources and usage events by environment, service, tenant class, and owner.

## 20. Testing strategy

**Unit tests** cover state transitions, budget enforcement, dependency scheduling, schema validation, memory filtering, policy decisions, redaction, and retry classification.

**Integration tests** cover checkpoints, outbox publication, worker leases, duplicate delivery, object uploads, model adapters, queue adapters, and approval expiration.

**Security tests** verify cross-tenant denial, prompt-injection resistance, SSRF protections, path containment, secret redaction, and sandbox escape defenses.

**Failure tests** terminate workers mid-step, delay queues, throttle models, expire credentials, corrupt tool output, and restore checkpoints.

**Agent evaluations** use frozen task sets and judge outputs with deterministic tests first. Model-based judging may supplement but must not replace objective checks.

**Deployment tests** create a run, execute a read-only tool, persist an artifact, retrieve permitted memory, complete verification, restart a worker during execution, and confirm successful resume.

## 21. Delivery phases

### Phase 1: Reliable single-agent core

- Typed domain state and plan schemas
- FastAPI run API
- LangGraph workflow and PostgreSQL checkpoints
- One read-only tool
- Model gateway with one provider
- Deterministic budgets and termination
- Unit and smoke evaluations

### Phase 2: Tools, verification, and local operations

- Queue-backed workers and transactional outbox
- Tool policy, idempotency, and sandbox interface
- Independent verifier
- Docker Compose stack
- OpenTelemetry instrumentation
- Approval workflow

### Phase 3: Memory and collaboration

- Scoped episodic and semantic memory
- Planner, researcher, executor, verifier, and memory roles
- Dependency-aware parallel scheduling
- Memory review and deletion interfaces
- Expanded regression evaluations

### Phase 4: Managed cloud deployment

- Azure and AWS infrastructure modules
- Workload identity, private networking, and managed secrets
- Canary delivery and autoscaling
- Backup/restore exercises and operational dashboards
- Security and production-readiness review

## 22. Key risks and mitigations

| Risk | Mitigation |
|---|---|
| Agent loops or excessive spend | Hard iteration, token, cost, time, and fan-out limits |
| Prompt injection through tools | Treat content as data, isolate instructions, validate every action, and restrict destinations |
| Incorrect side effects | Approval binding, idempotency, independent verification, and reconciliation |
| Poisoned or leaked memory | Scope filters, provenance, review, expiry, redaction, and deletion support |
| Duplicate queue delivery | Idempotency keys, task leases, and transactional completion |
| Model-provider outage | Circuit breakers, queued backpressure, and qualified provider fallback |
| Cross-tenant access | Authorization at API and persistence layers plus isolation tests |
| Multi-agent coordination cost | Structured task packets, bounded fan-out, and evidence-based role adoption |
| Cloud lock-in | Provider ports, adapters, and shared contract tests |
| Irreversible schema rollback | Backward-compatible migrations and expand-contract releases |

## 23. Decisions and open questions

### Accepted initial decisions

- Use Python 3.12, FastAPI, Pydantic, and LangGraph.
- Use PostgreSQL as the durable source of truth and pgvector for initial semantic memory.
- Use Redis locally; use managed Redis only for ephemeral data and leases, never authoritative workflow state.
- Use object storage for artifacts.
- Represent specialist agents as roles before splitting them into services.
- Require deterministic verification and approval gates outside model control.
- Package API and worker entry points in one image, with different commands and identities.

### Questions to resolve before implementation

1. Which first user workflow and tools define the evaluation set?
2. Is this single-user, team, or multi-tenant, and what data isolation standard applies?
3. Which data classifications may be sent to each model provider?
4. Which operations require approval in the first release?
5. What are the expected concurrent runs, duration, and monthly model budget?
6. Is generated-code execution required initially, or can it be deferred?
7. What retention and deletion obligations apply to runs, memories, and artifacts?
8. Which cloud is the primary production target and which is portability-only?

## 24. Production readiness checklist

- [ ] Acceptance tests and unsafe-action tests meet release thresholds.
- [ ] Every tool has schemas, risk classification, timeout, and ownership.
- [ ] Budgets and cancellation are enforced outside model prompts.
- [ ] Database migrations and backward compatibility are verified.
- [ ] Workload identities have least-privilege policies.
- [ ] Cloud data services use private networking and encryption.
- [ ] Secrets and sensitive content are absent from images, logs, and traces.
- [ ] Queue retries, dead-letter handling, and idempotency are tested.
- [ ] Backup restoration and checkpoint resume are demonstrated.
- [ ] Dashboards, alerts, runbooks, and service ownership are assigned.
- [ ] Deployment uses signed immutable image digests and a canary.
- [ ] Cost caps, provider quotas, and autoscaling maximums are configured.
- [ ] Memory inspection, correction, expiration, and deletion are operational.
- [ ] Regional service and model availability have been revalidated.