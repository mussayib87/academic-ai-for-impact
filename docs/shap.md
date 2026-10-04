# SHAP

`ai/explainability/service.py` loads the trained pipeline and the same model input used for prediction. It explains the classifier output using SHAP and the training background persisted with the model; there are no hand-authored feature contributions.

For each local prediction, SHAP targets the probability of the predicted class (`risk_level`), using the same `pipeline.classes_` order and label encoder as inference. Local output includes `target_class`; the base value and signed contributions reconstruct `risk_probability` for that class, and the summary and waterfall use those same contributions. Global importance averages absolute contributions to each row's own predicted-class probability.

`GET /api/v1/students/{id}/shap` is teacher-only. It stores the prediction and SHAP values/model version, adds a risk snapshot, and updates the teacher-visible current risk. Students receive no teacher-only SHAP output.