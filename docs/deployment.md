# Deployment

The Docker Compose file defines PostgreSQL, FastAPI, and Next.js. Set `JWT_SECRET` and `POSTGRES_PASSWORD` in a private `.env` before `docker compose up --build`. The backend container runs `alembic upgrade head` explicitly before Uvicorn; demo seeding is separate and opt-in.

The API accepts a `postgresql+psycopg://` URL. Local development defaults to SQLite. Persist PostgreSQL and upload volumes, restrict CORS to the deployed frontend origin, and provide a unique signing secret through the deployment secret manager.

The local LLM is not containerized. Ollama/model weights may require substantial host memory and disk; run it separately and configure a backend-reachable base URL. The checked-in development template remains visibly identified when Ollama is not selected.

Before any production/student-data use, establish privacy review, model validation, access review, backups, HTTPS, key rotation, logging/retention, and institution-approved retrieval sources. The demo dataset and its metrics are not production evidence.