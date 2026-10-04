# Phase 3: Real-Data Validation and Controlled ML Improvement

## Current Status

Phase 3 validation and candidate-model infrastructure is present, but real-data training is blocked. The checked local database state on 2026-10-02 contains 248 student records, 1,240 subject-period rows, no independent risk outcomes, and one academic period (`2026-S1`). Five subjects have records; the catalog contains six subjects. FA1, FA2, and assignment are populated on the 1,240 rows; attendance is absent. The populated academic fields lack source observation timestamps. The candidate training route therefore returns a blocked response. These counts do not by themselves establish that the input marks are genuine institutional evidence; source provenance must be verified before treating them as such.

The current production artifact remains `risk-20260929T181441Z`. It was trained on data identified by its artifact metadata as demo data. Its metrics are not evidence of real-data performance or readiness. Phase 3 does not replace the artifact, change predictions, create outcomes, or generate candidate SHAP when no validated candidate exists.

## Dataset Contract

The validation row unit is one student + one subject + one academic period, joined to an independent global student-period outcome by exact student and period. The target remains `AcademicRiskOutcome.risk_level`; no subject-level target is inferred. Multiple subject rows sharing one global target are not independent model samples.

Academic predictors are limited to the stored FA1, FA2, assignment, and attendance values whose own source observation dates are present and no later than the matched outcome. Database `created_at`/`updated_at`, import timestamps, and batch timestamps are provenance only; they never establish predictor availability. A predictor dated after an outcome is removed from the candidate CSV row and the target is withheld for that row. Rows with missing source dates, future observations, invalid periods/ranges, prohibited outcome sources, or unverifiable revisions are not training eligible.

Accepted academic periods follow `YYYY-S1` or `YYYY-S2`. Ranges are FA1 0-25, FA2 0-25, assignment 0-25, and attendance 0-100. Outcome sources containing model-prediction, SHAP, inference, synthetic-prediction, AI-generated-label, classifier-output, or mark-derived indicators are rejected from the target contract.

## Fingerprints and Coverage

`GET /api/v1/ml/phase3/readiness` and `GET /api/v1/ml/phase3/coverage` return measured counts, period/subject/class and department/section sample coverage, validation evidence, blockers, and a deterministic SHA-256 fingerprint. `GET /api/v1/ml/phase3/dataset` defaults to source-observation rows. A caller may explicitly request `aggregation_strategy=equal_subject_mean` and repeated `feature_contract` query values to inspect derived global rows; this is still a proposal and remains ineligible unless the exact strategy and feature contract have been approved. CSV rows contain dataset ID/version/fingerprint, derived features when requested, aligned target/time, and source record/outcome batch references. The fingerprint is based on normalized source values, timestamps, provenance checksums, independent outcomes, revision snapshots, and relevant import validation rows; request creation time and DB update timestamps are not part of the fingerprint.

Rejected import rows retain row number, USN when known, subject, period, reason, source filename, and batch reference. Duplicate rows already collapsed by earlier importer behavior can be counted from batch metadata, but original duplicate row payloads are not reconstructible if the importer did not persist them.

## Readiness Gates

Readiness requires at least 100 complete, temporally aligned, aggregated student-period observations; at least three distinct periods; 20 distinct students per risk class; valid values/outcomes; no duplicate/conflicting groups; source and actor provenance; no unresolved corrected-record as-of uncertainty; an approved target/feature contract; and an approved mapping from subject-period records to the existing global student-period target. A reproducible fingerprint is returned as evidence, not as proof of source authenticity.

## Phase 3 Methodology Decision: `equal_subject_mean`

The implemented Phase 3 aggregation strategy is `equal_subject_mean`. It is not an implicit default and is only accepted when a teacher explicitly approves it through the Phase 3 governance policy API or UI. The implementation aggregates records per `student_identifier` + `academic_period`: for each student-period group, it computes the arithmetic mean across all temporally aligned subject rows that share that same student and period. Each available subject record contributes equally to the mean; there is no subject-specific weighting or rank-based selection. Missing subjects are not imputed, weighted, or filled with zero; if a subject is absent from the student-period group, it simply contributes no value to the denominator. The current implementation does not enforce any minimum subject-coverage rule: coverage can be one subject, several subjects, or any observed subset, and the mean is taken over the available records only. This is an implementation rule, not a scientifically validated claim about missing-subject behavior.

The candidate feature contract is the ordered list `fa1_mean`, `fa2_mean`, `assignment_mean`, and `attendance_mean`. These are subject-aggregate academic-input features derived from the stored mark/attendance values for that student-period, not outcome-derived features and not production model features. They are permitted only when their source observation dates are present and not later than the matched independent outcome date. Any record where a source mark or attendance observation is dated after the outcome is removed from the candidate window and the outcome is withheld for that row. Candidate features remain separate from the current production model contract, which is defined in `ai.risk.features` as `attendance`, `assessment`, `previous_gpa`, `current_gpa`, `assignments_completed`, `activity_per_week`, `missing_submissions`, `attendance_change`, `assessment_change`, and `momentum_score`.

No aggregation strategy or candidate feature contract is approved by default. The system must not silently choose subject averaging, weakest-subject, weighting, or another mapping. A teacher can record a persisted, rationale-backed approval of that aggregation and a supported ordered feature contract through the governance UI or policy API; approval is append-only and audited. The latest approval permits readiness checks to evaluate the selected methodology, but it does not create or certify evidence, clear independent-outcome/temporal/coverage/provenance blockers, or make training ready by itself. FA1/FA2 remain academic context and are not features of the current production model. Methodology approval is separate from data-readiness approval, separate from candidate training, and separate from production promotion.

## Temporal Evaluation and Candidate Training

`ai.risk.candidate.train_candidate` is an isolated candidate-only utility. It requires an explicit feature contract, target definition, aggregation strategy, and dataset fingerprint. It rejects duplicate student-period rows and splits chronologically: earlier periods for train, the penultimate period for validation, and the latest period for test. At least three periods are mandatory. Candidate artifacts are written only under `models/candidates/`; the production `models/risk/risk_model.joblib` path is never used by this utility.

Candidate reports include split periods/sample counts/class distributions, accuracy, macro/weighted F1, per-class precision/recall/F1 and support, confusion matrix, balanced accuracy, multiclass Brier score, calibration error, and ROC-AUC/PR-AUC only when the split contains all classes needed to calculate them. Candidate SHAP uses the candidate pipeline and background only, reconstructs the selected candidate class probability, and is unavailable when no validated candidate exists.

The HTTP training route checks measured readiness and refuses training while any gate is blocked. The current database has zero independent outcomes, one period, no attendance values, no academic source dates, and no approved aggregation strategy, so no real candidate is trained. Synthetic rows are used only in isolated unit fixtures to test mechanics.

## Registry and Promotion

Candidate registry metadata includes artifact and dataset fingerprints, feature contract, target/aggregation definitions, split periods, algorithm/seed/software, metrics, creator, validation state, approval state, and history timestamps. Client-supplied metrics/artifact claims are not accepted as evaluation evidence. Validation, training, dataset generation, promotion, and rollback attempts are auditable.

Local deployment requires current readiness, independent outcomes, no leakage, temporal/class coverage, complete candidate artifact/provenance, completed evaluation and validation, explicit approval, a candidate artifact SHA-256 match, metadata/registry agreement, and exact compatibility with the live prediction feature and class contracts. The backend provides a LOCAL-only deployment selector with a persisted active version, transactional deployment events, candidate rejection, deployment history, and rollback to a verified prior deployment. A missing selector continues to use the original production artifact; an active candidate that becomes unsafe fails explicitly rather than silently falling back. Rollback is unavailable unless a successful prior deployment and its target artifact are verified.

Apply the new schema with `alembic upgrade head` before using deployment history, rejection, promotion, rollback, or methodology-approval APIs. The migrations add registry governance fields, local deployment state/history tables, and append-only methodology approval records; they do not seed the deployment selector or a methodology approval.

The local adapter does not copy, overwrite, or retrain `models/risk/risk_model.joblib`; it selects a hash-verified candidate artifact under `models/candidates/` for backend inference and can restore the original production artifact as the fallback. Artifact changes after approval are detected and inference fails closed until rollback. The currently defined Phase 3 candidate feature contract (`fa1_mean`, `fa2_mean`, etc.) differs from the live predictor contract, so these candidates are intentionally rejected for deployment until a candidate is produced with the compatible live feature schema and passes every gate. The readiness function and gates remain unchanged.

This is a local adapter only, not a cloud deployment, model-serving platform, or production-grade distributed rollout. It provides no cloud orchestration, traffic shifting, multi-instance synchronization guarantee, external approval identity, or operational monitoring/rollback automation. The deployment APIs remain teacher-only under the current application policy.

## Candidate and Production Comparison

`GET /api/v1/ml/phase3/compare` reports `status: unavailable` unless comparison evidence can establish identical feature contracts and a verified common held-out dataset. The current production metrics are artifact-recorded demo evaluation metrics and do not identify the candidate temporal test rows; they are shown only as their own provenance-bound reference, never as a winner or validation of real imported data. The response exposes explicit feature-contract and dataset-identity/hash compatibility fields, blockers, candidate test metrics (including stored per-class support and confusion matrix when present), and production/candidate provenance. No common-set metric or winner is fabricated when shared test rows cannot be verified.

## Endpoints

- `GET /api/v1/ml/phase3/readiness`
- `GET /api/v1/ml/phase3/coverage`
- `GET /api/v1/ml/phase3/dataset`
- `POST /api/v1/ml/phase3/train`
- `GET /api/v1/ml/phase3/candidate`
- `GET /api/v1/ml/phase3/evaluation`
- `GET /api/v1/ml/phase3/compare`
- `GET /api/v1/ml/phase3/shap`
- `POST /api/v1/models/registry/{id}/validate`
- `POST /api/v1/models/registry/{id}/approve`
- `POST /api/v1/models/registry/{id}/promote`
- `POST /api/v1/models/registry/{id}/reject`
- `POST /api/v1/models/registry/{id}/rollback`
- `GET /api/v1/models/deployments`
- `GET /api/v1/ml/phase3/policy`
- `POST /api/v1/ml/phase3/policy/approve`

All routes are teacher-only. A blocked API result is not a readiness claim. The Phase 3 interface distinguishes current production, candidate, and imported academic evidence, shows local deployment history and audit provenance, and labels predictions as transitions rather than observed outcomes. Methodology approval requires an explicit confirmation, a non-empty rationale, a supported aggregation strategy, and a unique supported feature contract; it is kept separate from candidate approval and deployment. The comparison view is unavailable unless compatible evaluation rows and outcome provenance are verifiable.
