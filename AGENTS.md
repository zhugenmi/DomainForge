# DomainForge — Agent Guide

This repo is an enterprise agent development platform. Backend: FastAPI + SQLAlchemy async + pgvector. Frontend: Next.js 16 App Router + Tailwind 4.

## Quick start

```bash
# Infrastructure
docker compose up -d                    # pgvector:5432 + redis:6379

# Backend
cp .env.example .env                   # fill LLM_API_KEY
python3 -m venv .venv && source .venv/bin/activate
make install                           # pip install -e ".[dev]"
make migrate                           # alembic upgrade head
make dev                               # uvicorn app.main:app --reload :8000

# One-shot: ./domainforge.sh starts docker + backend + frontend, Ctrl+C stops all.
# ./domainforge.sh stop / restart [b|f|all] / status
```

## Commands

| Command | What |
|---------|------|
| `make install` | Install Python deps + dev deps |
| `make dev` | uvicorn hot-reload on `:8000` |
| `make test` | pytest -v --cov=app --cov-report=term-missing |
| `make lint` | `ruff check app tests` then `mypy app` (strict mode) |
| `make migrate` | alembic upgrade head |
| `make makemigration msg="..."` | alembic autogenerate |
| `make docker-up` / `make docker-down` | docker compose |
| `make frontend-install` / `make frontend-dev` / `make frontend-build` | Next.js 16 |

**Lint first, then build/test.** `ruff` checks formatting + import sort. `mypy` is strict. Run before CI-like commits.

**Scripts** (`scripts/`) run as `python scripts/<name>.py [args]` — they add root to `sys.path` themselves.

## Project structure

```
domainforge/
├── app/                  # FastAPI backend (main.py entrypoint)
│   ├── api/              # Routers, prefix /api/v1
│   ├── runtime/          # AgentRuntime: State+Node+Router (4 phases)
│   ├── llm/              # LLM providers, embedding, rerank, model router
│   ├── tools/            # Builtin + MCP + ToolRegistry
│   ├── rag/              # Parsing, chunking, retrieval (hybrid: vector+BM25+RRF+Rerank)
│   ├── memory/           # Three-tier: short-term / summary / long-term (vector)
│   ├── skills/           # Pluggable instruction packages (not tools)
│   ├── security/         # JWT, RBAC (admin/operator/user), prompt guard
│   ├── schemas/          # Pydantic request/response models
│   ├── configs/          # Pydantic-Settings (settings.py)
│   ├── database/         # SQLAlchemy async + Alembic + repositories
│   ├── observability/    # OpenTelemetry tracing, metrics, audit logging
│   ├── evals/            # Eval datasets + runner + analyzer
│   └── services/         # Redis, cache, attachment/preview/import stores
├── frontend/             # Next.js 16 App Router
├── scripts/              # Offline: build_index, import_documents, run_evals, benchmark
├── tests/                # pytest, each domain mirrors app/ structure
├── skills/               # installed/ + marketplace/ for skill packages
└── docs/                 # Architecture docs, ADRs, fix records, eval reports
```

## AgentRuntime execution flow

```
User Query → IntentNode → PlannerNode → MemoryNode
  → RetrievalNode (+ WebSearchNode) → ToolNode (ReAct loop)
  → ReasoningNode → AnswerNode → ReflectionNode
```

Three orchestration modes: ReAct (tools), Plan & Execute (complex), Hybrid (dynamic switch). State is a single `AgentState` dataclass passed through the node chain. SSE streaming via EventBus.

## Testing

- **pytest-asyncio** with `asyncio_mode = "auto"` (no need for `@pytest.mark.asyncio`)
- DB tests: `conftest.py` provides `db` fixture → SQLite `:memory:` via aiosqlite, auto create/drop all tables
- Test fixtures: `sample_user_id` = `00000000-...-0001`, `sample_session_id` = `00000000-...-0002`
- Tests that require async `AsyncSession` use `pytest_asyncio.fixture`

## Config quirks

- `AVAILABLE_MODELS`: comma-separated for agent form dropdown; empty → falls back to `DEFAULT_LLM_MODEL`
- `EMBEDDING_BATCH_SIZE=10` / `EMBEDDING_BATCH_INTERVAL=0.2`: DashScope RPM limit workaround
- `JWT_SECRET`: prod enforces ≥32 bytes; `JWT_SECRET_OVERRIDE=true` to bypass in emergencies
- `ADMIN_API_KEY`: admin role login (dev allows any username)
- `EVALS_LLM_JUDGE`: LLM-as-judge metric costs 2 extra LLM calls per eval case
- `MCP_SERVER_URL`: optional, fetches remote tools on startup
- `RERANK_BASE_URL`: empty → rerank is skipped (identity passthrough)

## Docs

All in Chinese under `docs/`. Navigation hub at `docs/README.md`:
- `docs/architecture/` — as-built system design (7 docs)
- `docs/adr/` — architecture decision records (6 ADRs)
- `docs/fix/` — bug postmortems with root cause + validation + retrospective
- `docs/plan/` — design.md (origin) + full-implementation.md (progress)

Refactor-checklist: read the "current limitations" section of the relevant `architecture/0X_*.md`, then check `fix/` for historical issues.

## RBAC

Three roles: `admin` > `operator` > `user`. Admin granted via `ADMIN_API_KEY`. `require_role("admin")` FastAPI dependency on sensitive endpoints.

## Skills

Skills are **instruction packages** (not tools). They inject system-prompt instructions into the agent. Installed from DB (`installed_skill` table) on startup. Marketplace under `skills/marketplace/`. See `docs/architecture/07_skills.md`.

## Frontend

Next.js 16 (App Router), React 19, Tailwind 4. Built-in `AGENTS.md` warning: this Next.js version may have breaking API changes from older docs — check `node_modules/next/dist/docs/` before writing code.
