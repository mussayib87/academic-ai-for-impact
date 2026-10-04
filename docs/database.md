# Database

SQLAlchemy entities are defined in `backend/app/models/entities.py`; schema changes are tracked in `backend/migrations/versions/`. Apply revisions with `alembic upgrade head`. Never rely on application startup to create production tables.

The schema includes users, students, teachers, courses, subjects, attendance, marks, assessments, dated learning activity, assignments/enrollments, submissions/versions, rubrics/scores, feedback, model predictions/snapshots, SHAP values, academic momentum, interventions/drafts/reviews, retrieval documents/chunks, notifications, and audit logs.

The subject-academics migrations add normalized per-student/per-subject/per-period FA1, FA2, assignment mark, and attendance fields with import-batch, actor, and source-observation timestamps. `YYYY-S1`/`YYYY-S2` is the single academic-period key; preexisting periodless rows are preserved as `UNSPECIFIED` and excluded from period-qualified training exports. Corrections append immutable record-history snapshots. A separate `academic_risk_outcomes` table stores independently sourced student-period targets; current classifier outputs are never copied into it. Assignment rows can reference a catalog subject while preserving legacy string values. Submission page batches retain individual files as versions and record page position/count. The official EVS, CN, TOC, RM, and SE subjects are inserted only when absent; existing subject/student records are not removed.

Most entities use `created_at`/`updated_at`, foreign keys, and indexes on common ownership/filter fields. A student user is linked by a unique `students.user_id`; role-based dependencies resolve the current profile from that relationship.

The default SQLite URL is for local work. PostgreSQL URLs use `postgresql+psycopg://...`. SQLite's `check_same_thread` option is set only for SQLite.