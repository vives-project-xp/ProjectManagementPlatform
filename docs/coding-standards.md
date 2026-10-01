# Coding standards

Rules every change must follow. Deviations need an ADR in `docs/adr/`.

## Stack

- Python 3.12, dependencies managed with `uv`.
- Ruff for linting and formatting; pytest for tests.
- Repository layout: `backend/` and `frontend/` as separate Python packages, each with its own Dockerfile; `compose.yml` and `Caddyfile` at the root.

## Database

- PostgreSQL is the required relational database.
- Do not introduce SQLite, MySQL, MariaDB, or another database without an approved deviation.
- Database schema changes must use Alembic migrations.

## Backend

- Python, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic / pydantic-settings.
- API endpoints should primarily handle HTTP concerns. Business logic belongs in service modules where appropriate.
- Configuration and secrets come from environment variables via pydantic-settings; never commit secrets, `.env` files or `logins.txt`.
- Passwords are hashed with Argon2. Authentication uses a JWT bearer token (valid 8 hours) issued by the backend.

## Frontend

- NiceGUI; the frontend talks to the backend only through the REST API and never accesses the database (ADR 0003).
- Follow the VIVES house style: Poppins, VIVES red `#e00020`, black `#1e1e1e`, white, sand `#efeee9`; no font weight above semibold; accent colors never on text.
- Interface text is in English.

## Tests

- Backend: API-level tests against a real PostgreSQL (no database mocks), in CI on every pull request.
- Frontend: NiceGUI tests for login and the main flows.
