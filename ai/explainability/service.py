from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shap

from ai.risk.features import FEATURES
from ai.risk.predict import DEFAULT_ARTIFACT, load_artifact


def _explain_class_probability(classifier: Any, background: np.ndarray, rows: np.ndarray, class_index: int) -> shap.Explanation:
    def class_probability(masked_rows: np.ndarray) -> np.ndarray:
        return classifier.predict_proba(masked_rows)[:, class_index]

    explainer = shap.Explainer(class_probability, background, feature_names=FEATURES, algorithm='permutation')
    return explainer(rows, max_evals=2 * len(FEATURES) + 1)


def _explain(frame: pd.DataFrame, artifact_path: Path = DEFAULT_ARTIFACT, target_class: str | None = None) -> tuple[dict[str, Any], np.ndarray]:
    artifact = load_artifact(artifact_path)
    pipeline = artifact['pipeline']
    classifier = pipeline.named_steps['classifier']
    transformed = pipeline.named_steps['imputer'].transform(frame[FEATURES])
    classes = [str(label).upper() for label in artifact['label_encoder'].inverse_transform(np.asarray(classifier.classes_, dtype=int))]
    probabilities = classifier.predict_proba(transformed)[0]
    target_class = target_class.upper() if target_class else classes[int(np.argmax(probabilities))]
    if target_class not in classes:
        raise ValueError(f'Unknown SHAP target class: {target_class}')
    target_index = classes.index(target_class)
    values = _explain_class_probability(classifier, artifact['background'], transformed, target_index)
    contributions = np.asarray(values.values)[0]
    base_value = float(np.asarray(values.base_values).reshape(-1)[0])
    return {
        'target': f'P({target_class})',
        'target_class': target_class,
        'base_value': base_value,
        'contributions': {name: float(value) for name, value in zip(FEATURES, contributions)},
        'feature_values': {name: float(value) for name, value in zip(FEATURES, frame.iloc[0][FEATURES])},
        'model_version': artifact['metadata']['model_version'],
    }, np.asarray(values.values)


def explain_student(features: dict[str, float], artifact_path: Path = DEFAULT_ARTIFACT, target_class: str | None = None) -> dict[str, Any]:
    missing = sorted(set(FEATURES) - set(features))
    if missing:
        raise ValueError(f'Missing model features: {", ".join(missing)}')
    frame = pd.DataFrame([{name: float(features[name]) for name in FEATURES}], columns=FEATURES)
    explanation, _ = _explain(frame, artifact_path, target_class)
    ranked = sorted(explanation['contributions'].items(), key=lambda item: abs(item[1]), reverse=True)
    explanation['summary'] = [
        f'{name.replace("_", " ").capitalize()} increased the predicted risk.' if contribution > 0 else f'{name.replace("_", " ").capitalize()} reduced the predicted risk.'
        for name, contribution in ranked[:5]
    ]
    explanation['waterfall'] = [
        {'feature': name, 'value': explanation['feature_values'][name], 'contribution': contribution}
        for name, contribution in ranked
    ]
    return explanation


def global_importance(rows: list[dict[str, float]], artifact_path: Path = DEFAULT_ARTIFACT) -> dict[str, Any]:
    if not rows:
        raise ValueError('At least one feature row is required')
    frame = pd.DataFrame([{name: float(row[name]) for name in FEATURES} for row in rows], columns=FEATURES)
    artifact = load_artifact(artifact_path)
    pipeline = artifact['pipeline']
    classifier = pipeline.named_steps['classifier']
    transformed = pipeline.named_steps['imputer'].transform(frame[FEATURES])
    predicted_classes = np.argmax(classifier.predict_proba(transformed), axis=1)
    values = np.zeros((len(frame), len(FEATURES)))
    for class_index in np.unique(predicted_classes):
        row_indices = np.flatnonzero(predicted_classes == class_index)
        explanations = _explain_class_probability(classifier, artifact['background'], transformed[row_indices], int(class_index))
        values[row_indices] = np.asarray(explanations.values)
    scores = np.mean(np.abs(values), axis=0)
    return {
        'target': 'probability of each row predicted class',
        'features': [{'name': name, 'importance': float(score)} for name, score in sorted(zip(FEATURES, scores), key=lambda item: item[1], reverse=True)],
    }