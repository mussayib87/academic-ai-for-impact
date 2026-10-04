# Architecture

The Next.js App Router frontend uses a role-aware horizontal shell and calls the FastAPI service with bearer tokens stored by the current browser session. Teacher and student route groups are separate; backend dependencies, not the UI, enforce access.

FastAPI routes live in `backend/app/main.py`, with login in `backend/app/api/auth.py`, identity dependencies in `backend/app/core/security.py`, SQLAlchemy session/metadata in `backend/app/database/`, and entities/schemas/services in their corresponding packages.

The database is migrated by Alembic. Startup registers routes and middleware but does not create schema or seed data. Demo seeding is an explicit module command. SQLAlchemy selects SQLite-only connection options only for SQLite URLs; PostgreSQL uses psycopg.

Risk features flow from dated academic observations to preprocessing, evaluated sklearn models, prediction, SHAP explanation, and faculty review. RAG retrieves only from files placed in the institution-managed knowledge base. The LLM provider is downstream of model evidence and never calculates risk.