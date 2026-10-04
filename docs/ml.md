# Risk Model

`ai/risk/preprocess.py` derives `data/processed/DSstudents_processed.csv` from student records and timestamped momentum, activity, assignment, and submission data. `features.py` defines a fixed allowlist; student IDs, current stored risk probability, and risk level are excluded from model inputs.

`ai/risk/train.py` uses a stratified holdout split and evaluates Logistic Regression and Random Forest. It also evaluates XGBoost when installed. Accuracy, weighted precision/recall/F1, label order, and confusion matrix are calculated from held-out predictions. Selection is by weighted F1, then the selected pipeline is refit on all supplied rows.

The Joblib bundle stores the preprocessing pipeline, label encoder, model version, feature names, evaluation metadata, and SHAP background rows. A neighboring JSON file stores readable training/evaluation metadata. Optional XGBoost is installed by `pip install -r requirements-ai.txt`.

Inference maps each `predict_proba` column through `pipeline.classes_` and the fitted label encoder. `risk_level` is the class with the maximum probability, and `risk_probability` is exactly that class's probability: `class_probabilities[risk_level]`. The response identifies this as `P(risk_level)` and reports `argmax(class_probabilities)` as the classification policy. Risk-band threshold settings have been retired; they do not alter model predictions.

`ai/risk/features.py::FEATURE_CONTRACT` records the current global feature sources and calculations. The existing artifact uses the ten listed global features; subject FA1, FA2, assignment marks, and attendance are stored/displayed as subject academic context but are not trained predictors. Subject-specific risk or SHAP claims must not be made without a separately trained and validated subject-level model.

Period-scoped marks are imported with `YYYY-S1`/`YYYY-S2` and may include source `*_observed_at` dates. Independent global risk outcomes are stored separately with their own observation date/source. `ai.risk.academic_dataset` exports one real student/subject/period row and joins only a same-student, same-period independent outcome. It emits no usable target unless all included academic values were observed and last updated no later than the outcome. This exporter is not connected to `train()` and does not change the current artifact. It reports readiness thresholds (100 complete aligned rows, 3 distinct periods, 20 distinct students per risk class, no invalid/duplicate records) and remains blocked until a documented, reviewed aggregation strategy can map subject-period inputs to the existing global student-period target. Existing records lacking an explicit academic period remain `UNSPECIFIED`; no period, mark, timestamp, or target is inferred.

Current evaluation is synthetic demo data and is intentionally easy to separate. It is not a validated institutional risk model and must not be used for consequential decisions.

## Phase 3: Real-Data Validation

See [phase3.md](phase3.md) for the canonical validation dataset, observed-at-only temporal rule, global student-period target contract, deterministic fingerprint, coverage evidence, readiness blockers, candidate-only temporal training, candidate SHAP, registry lifecycle, and disabled promotion/rollback adapter.

The Phase 3 candidate utility writes only to `models/candidates/`. It does not call the legacy `train()` function or write `models/risk/risk_model.joblib`. The legacy training command remains an explicit production-artifact writer and must not be run for Phase 3 candidate experiments. The HTTP candidate-training endpoint is gated by measured readiness and currently returns blocked because the database has no independent outcomes, only one period, no attendance values, missing source dates, and no approved aggregation strategy.