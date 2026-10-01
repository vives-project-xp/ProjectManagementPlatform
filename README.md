# Project Management Platform

A central web application for managing and following up student projects within **Project Experience** at VIVES University of Applied Sciences (EO-ICT, Project 6).

**Product owner:** Ronny Mees

## Why

Running student projects today means many separate steps and tools: creating teams and projects, setting up repositories, granting students access, tracking tasks, following up progress — and a lot of valuable photo and video material gets lost along the way.

This platform centralizes and automates that work so coaches can spend more time on actual coaching, and turns weekly student updates into a visual project log and AI-assisted communication material.

## Scope

### MVP — Project management & automation (coaches)
- Create, edit and manage projects
- Add and manage students and coaches per project
- Automatically create and configure a repository, with the right users and permissions
- Automatically create and initialize a Trello board
- Authentication and authorization
- Overview of active and historical projects

### Project log & AI content (students)
- Weekly progress updates with photos, short videos and a short description
- Chronological timeline per project
- Media storage with metadata
- Generative AI (via API) proposes social-media content from the weekly updates
- Review step to check and edit generated content before it is published
- Attention to privacy, image rights and responsible use of AI

### Possible extensions
- **v2 — Budget & orders:** project budget, expenses/orders, linked documents, budget visualization
- **v3 — Evaluation & feedback:** evaluation moments, feedback per student/team, progress over time

A high-quality, usable MVP takes priority over implementing as many features as possible.

## How we work

This project is built with an **AI-assisted development workflow** (Claude Code + Matt Pocock's skills):

```
Discovery → Specification → Tickets → Implementation → Verification → Integration
```

- `/grill-with-docs` for discovery, `/to-spec` for the specification, `/to-tickets` for implementation issues
- `/implement #<issue>` — **one issue at a time**, always an unblocked one
- Every change goes through automated checks, manual review and functional testing before a pull request into `main`
- GitHub Issues is the tracker; durable decisions are recorded in `CONTEXT.md` and ADRs

## Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16 (`backend/`)
- **Frontend:** Python 3.12, NiceGUI, talking to the backend only through its REST API (`frontend/`, ADR 0003)
- **Delivery:** Docker Compose behind Caddy (HTTPS), deployed to the VIVES VM by a self-hosted GitHub Actions runner (ADR 0001)
- **Tooling:** [uv](https://docs.astral.sh/uv/) for dependencies, Ruff for linting/formatting, pytest for tests

See `docs/coding-standards.md` for the rules every change follows.

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/getting-started/installation/) and Docker.

### Run the tests

```bash
docker compose -f compose.test.yml up -d     # PostgreSQL for tests on port 5433

cd backend  && uv sync && uv run pytest
cd frontend && uv sync && uv run pytest      # drives the real backend in-process
```

Lint and format check (as CI does):

```bash
uvx ruff check .
uvx ruff format --check .
```

### Run the whole stack locally

```bash
cp .env.example .env                          # then set a POSTGRES_PASSWORD
docker compose up -d --build
docker compose run --rm backend alembic upgrade head
```

Open <https://localhost> (accept the certificate warning; Caddy signs it with its own CA). The backend health check is at <https://localhost/api/health>.

## Deployment

- **CI** (`.github/workflows/ci.yml`) runs lint and all tests on GitHub-hosted runners for every pull request and every push to `main`.
- **Deploy** (`.github/workflows/deploy.yml`) starts only after CI succeeded for a push to `main`. It runs on the self-hosted runner `px6-vm` on the VM: builds the images, runs the migrations, restarts the services, and fails if `https://10.20.10.33/api/health` does not answer.
- Pull requests never run on the self-hosted runner (the repository is public).
- Secrets live only on the VM in `/opt/pmp/.env` (owned by the `github-runner` user); `.env` and `logins.txt` are gitignored.
- The live site is <https://10.20.10.33> (VIVES network only). Browsers warn about the certificate until VIVES IT provides a hostname.
