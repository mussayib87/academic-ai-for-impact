from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ai.risk.features import FEATURES

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT = ROOT / 'models' / 'risk' / 'risk_model.joblib'


@lru_cache(maxsize=4)
def _load_cached_artifact(path: str, modified_ns: int, size: int) -> dict[str, Any]:
    return joblib.load(path)


def load_artifact(artifact_path: Path = DEFAULT_ARTIFACT) -> dict[str, Any]:
    resolved_path = Path(artifact_path).resolve()
    stat = resolved_path.stat()
    return _load_cached_artifact(str(resolved_path), stat.st_mtime_ns, stat.st_size)


def predict(features: dict[str, float], artifact_path: Path = DEFAULT_ARTIFACT) -> dict[str, Any]:
    missing = sorted(set(FEATURES) - set(features))
    if missing:
        raise ValueError(f'Missing model features: {", ".join(missing)}')
    artifact = load_artifact(artifact_path)
    pipeline = artifact['pipeline']
    metadata = artifact['metadata']
    frame = pd.DataFrame([{name: float(features[name]) for name in FEATURES}], columns=FEATURES)
    probabilities = np.asarray(pipeline.predict_proba(frame)[0], dtype=float)
    label_encoder = artifact['label_encoder']
    class_ids = np.asarray(pipeline.classes_, dtype=int)
    classes = label_encoder.inverse_transform(class_ids)
    class_probabilities = {str(label).upper(): float(probability) for label, probability in zip(classes, probabilities)}
    predicted_index = int(np.argmax(probabilities))
    level = str(classes[predicted_index]).upper()
    risk_probability = class_probabilities[level]
    return {
        'risk_level': level,
        'risk_probability': risk_probability,
        'risk_probability_semantics': 'P(risk_level)',
        'risk_level_policy': 'argmax(class_probabilities)',
        'model_version': metadata['model_version'],
        'prediction_timestamp': datetime.now(timezone.utc),
        'class_probabilities': class_probabilities,
    }