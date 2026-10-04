# Academic AI for Impact

An early-warning and academic support demo built on the existing repository. It provides separate faculty and student workspaces, protected student records, assignment uploads and grading, dated momentum signals, a trainable risk model, SHAP explanations, institutional-source retrieval, and reviewed intervention drafts.

All current sample records are fictional **DEMO DATA**. The demo classifier is trained and evaluated against generated labels; its reported scores are not evidence of performance on a real institution. Do not connect this build to live student records without institutional privacy, governance, security, accessibility, and model-validation review.

## Requirements

- Python 3.10 or newer
- Node.js 20 or newer and npm
- SQLite for local work; PostgreSQL is supported for deployment
- Optional for semantic document embeddings: install `requirements-ai.txt` and download the configured Sentence Transformers model
- Optional for XGBoost comparison: install `requirements-ai.txt`
- Optional local LLM: Ollama installed separately with a local model pulled
- Optional research interface: install `requirements-demo.txt`

## Local Setup (PowerShell)

From the repository root:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Replace `JWT_SECRET` in `.env` with a unique, random secret before deployment. Then:

```powershell
Push-Location frontend
npm ci
Pop-Location
```

## Database and Demo Data

Schema changes are explicit Alembic migrations. Application startup does not create tables or seed users.

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m backend.app.services.seed_demo
```

The seed command is deterministic and creates 248 fictional students and dated observations, assignments, submissions, snapshots, and draft interventions. Seed labels are historical example data; current HIGH/MEDIUM/LOW distribution is calculated from canonical model predictions and can differ. The checked-in database currently predicts 52 HIGH, 83 MEDIUM, and 113 LOW.

Demo sign-ins:

- Faculty: `teacher@example.com` / `teacher123`
- Student: `student@example.com` / `student123`

These credentials are only for local demo data. Do not reuse them in a deployed environment.

## Run the Services

Terminal 1, repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
Push-Location frontend
npm run dev
Pop-Location
```

Open <http://localhost:3000>. The API health endpoint is <http://localhost:8000/health>; authenticated API documentation is available at <http://localhost:8000/docs>.

## Academic Data Imports

Apply schema updates with `alembic upgrade head`, then open **Academic Data** in the faculty workspace. CSV and XLSX imports support marks, assessments, attendance, and learning activities; the page displays the required columns for each record type. Student matching uses existing student IDs, import batches retain source/checksum/row status metadata, and repeated files or rows are not applied twice. Imported observations feed current risk features without replacing student profile values or assignment submission uploads.

The **Internal Marks** register stores subject-scoped EVS, CN, TOC, RM, and SE records by academic period (`YYYY-S1` / `YYYY-S2`). Import `subject_records` from CSV/XLSX with `USN`, `Subject`, `Academic_Period`, and any of `FA1`, `FA2`, `Assignment`, and `Attendance`; per-field `*_Observed_At` dates are retained for temporal alignment. Corrections update only the same student/subject/period and append revision history. Independent risk outcomes can be imported as `risk_outcomes` only with a documented source; model predictions and labels derived from the same marks are rejected as targets. Internal marks use `((FA1 + FA2) / 2) + Assignment`; subject marks remain outside the existing global risk model.

The future-only observation export and readiness report are available at `GET /api/v1/ml/academic-data/export.csv` and `GET /api/v1/ml/academic-data/readiness`, and the CLI exporter is `python -m ai.risk.academic_dataset`. They never train a model. Readiness requires complete, time-aligned marks plus independent outcomes, three periods, at least 100 aligned observations, 20 distinct students in each risk class, clean values/identities, and an approved global aggregation strategy. Current data is not ready.

Phase 3 adds teacher-only real-data validation, coverage, deterministic dataset fingerprints, safe candidate CSV export, temporal candidate-training utilities, candidate evaluation/SHAP contracts, and blocked promotion/rollback controls. See [docs/phase3.md](docs/phase3.md). Candidate training is separate from the production model; current measured data does not pass readiness, so no real-data candidate is trained.

## Research and Demo Interface

The optional Streamlit app calls the existing FastAPI endpoints for faculty authentication, risk distribution, student records, canonical prediction, SHAP explanation, momentum, and intervention drafts. Install its optional dependencies and run from the repository root:

```powershell
python -m pip install -r requirements-demo.txt
streamlit run streamlit_app.py
```

Set `ACADEMIC_AI_API_URL` if FastAPI is not at `http://127.0.0.1:8000`. When a current HIGH-risk prediction exists, the app selects the existing student with the highest P(HIGH); otherwise it selects the existing record with the highest P(HIGH) and preserves its actual predicted class. Intervention drafts still require faculty review and approval in the faculty workspace.

## Model Pipeline

The preprocessor derives explicit features from database students and dated academic observations, excluding student IDs and risk-probability proxies from model inputs:

```powershell
.\.venv\Scripts\python.exe -m ai.risk.preprocess
.\.venv\Scripts\python.exe -m ai.risk.train
```

The processed dataset target is `data/processed/DSstudents_processed.csv`. Training evaluates Logistic Regression and Random Forest with a stratified holdout split, and XGBoost if it is installed. The best weighted-F1 candidate is saved to `models/risk/risk_model.joblib`; its class-label map, feature list, training metadata, holdout metrics, and confusion matrix are saved with the model and in `models/risk/risk_model.metrics.json`.

This legacy training command writes directly to the production artifact path. Do not use it for Phase 3 candidate work. Phase 3 candidates use the isolated candidate pipeline and require real-data readiness plus explicit governance; see [docs/phase3.md](docs/phase3.md).

The bundled seed data is intentionally separable synthetic data. Its perfect holdout metrics are a pipeline smoke-test result only, not a meaningful estimate of real student risk prediction quality.

## Explanations and Momentum

SHAP uses the saved classifier, that student's actual model features, and persisted training background. Student 360 exposes the computed local contributions and a model-version tag. Momentum uses timestamped attendance, assessment, activity, and submission observations; fewer than four observations are classified as `INSUFFICIENT_DATA`.

## Institutional Retrieval and Local LLM

No institutional policy is included. Add institution-approved `.txt`, `.md`, `.pdf`, or `.docx` material under `knowledge_base/policies/`, `academic_support/`, `mentoring/`, or `resources/`, then run:

```powershell
.\.venv\Scripts\python.exe -m ai.rag.index_cli
```

Retrieval returns cited chunks and explicitly reports no match when no relevant source is present. The base install uses a labeled local hashing-vectorizer fallback. For Sentence Transformers, install `requirements-ai.txt`; the actual embedding provider is reported in retrieval metadata.

Set `LLM_PROVIDER=ollama` and `LLM_MODEL_NAME=ollama:<model-name>` for a separately installed Ollama model. Set `LLM_PROVIDER=gemini` with `GEMINI_MODEL_NAME` and a private `GEMINI_API_KEY` to opt into Gemini. With no usable external provider configured, intervention generation uses a development text template clearly marked as **not an LLM**. Risk is calculated by the classifier, never by the LLM. Generated messages remain drafts until a faculty member edits/reviews and explicitly approves them.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
Push-Location frontend
npm test
npm run typecheck
npm run lint
npm run build
Pop-Location
```

## Docker

Copy `.env.example` to `.env`, then set a unique `JWT_SECRET` and `POSTGRES_PASSWORD` before running:

```powershell
docker compose up --build
```

Compose explicitly migrates the PostgreSQL schema before starting the API. Seed demo data separately with `docker compose exec backend python -m backend.app.services.seed_demo`. The local LLM is intentionally not included in Docker; run Ollama on the host and configure an address reachable from the backend container when needed.

For the seeded demo model inside Compose, run:

```powershell
docker compose exec backend python -m ai.risk.preprocess
docker compose exec backend python -m ai.risk.train
```

## Current Scope and Limitations

- Demo data and the generated model are fictional; no real institutional dataset or policy corpus was provided.
- XGBoost and Sentence Transformers are optional extras. Without them the risk service compares the two sklearn baselines and RAG uses its explicit hashing fallback.
- PDF and common image/text files can be previewed inline. Other supported assignment files are downloaded; uploaded files are never executed.
- CSV export is implemented. PDF/Excel export, external message delivery, and production deployment hardening are not included.
- The legacy `setup_project.py` is not used by any setup, build, or runtime command. Do not execute it.