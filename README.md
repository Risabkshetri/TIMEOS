# TimeOS — Personal Time Intelligence System

A private, local-first system that reconstructs how time is spent across Android (primary), the
browser (secondary), and eventually a Linux desktop (deferred, post-V1) — then answers questions
about focus, fragmentation, distraction, and goal alignment using deterministic analytics, with an
LLM used only for interpretation behind a strict privacy gate.

**Full design:** [`docs/TIMEOS_ENGINEERING_SPEC.md`](docs/TIMEOS_ENGINEERING_SPEC.md) — read this
before touching any code. It defines the architecture, data model, privacy boundary, and the
phase-by-phase implementation plan this repository follows.

**Current status:** Phase 0 (repository scaffold) complete. See §38 of the spec for what's next
(Phase 1A: minimal installable Android app).

## Quick start (local development)

Requires Docker with the Compose plugin (`docker compose version`).

```bash
cp .env.example .env
# edit .env and set POSTGRES_PASSWORD to something real

cd deploy
docker compose -f compose.yml -f compose.dev.yml up -d --build
```

Then:

```bash
curl http://localhost:8000/v1/health/live    # {"status": "live"}
curl http://localhost:8000/v1/health/ready   # {"status": "ready"} once the DB migration runs
open http://localhost:3000                   # dashboard stub
```

## Repository layout

```
android/     Kotlin/Compose collector — PRIMARY (Phase 1+)
backend/     FastAPI monolith: ingestion, deterministic analytics, privacy gate, AI (Phase 3+)
dashboard/   Next.js web dashboard (Phase 5+)
extension/   WebExtension for Brave/Chromium + Firefox (Phase 9+)
desktop/     Linux desktop agent — DEFERRED, post-V1 (Phase 12)
deploy/      Docker Compose stack, Caddyfile, backup scripts
docs/        Engineering spec and Architecture Decision Records
tools/       Dev scripts, fixture generators
```

## Backend development (without Docker)

```bash
cd backend
pip install -e ".[dev]"
pytest                    # unit tests, including the privacy-isolation security tests
ruff check .
mypy timeos
lint-imports               # enforces ADR-006: timeos.ai may never import the data layer
```

## Secrets

Never commit `.env`. `.env.example` documents every variable with a placeholder. A pre-commit hook
and CI both run `gitleaks` — see `.pre-commit-config.yaml` and `.gitleaks.toml`.

```bash
pip install pre-commit
pre-commit install
```
