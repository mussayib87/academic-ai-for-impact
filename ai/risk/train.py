import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder

from ai.risk.features import FEATURES, TARGET, load_training_data

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / 'data' / 'processed' / 'DSstudents_processed.csv'
DEFAULT_ARTIFACT = ROOT / 'models' / 'risk' / 'risk_model.joblib'


def build_candidates() -> dict[str, Any]:
    models: dict[str, Any] = {
        'logistic_regression': LogisticRegression(max_iter=2000, class_weight='balanced', random_state=42),
        'random_forest': RandomForestClassifier(n_estimators=300, min_samples_leaf=2, class_weight='balanced', random_state=42),
    }
    try:
        from xgboost import XGBClassifier

        models['xgboost'] = XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, eval_metric='mlogloss', random_state=42)
    except ImportError:
        pass
    return {name: Pipeline([('imputer', SimpleImputer(strategy='median')), ('classifier', estimator)]) for name, estimator in models.items()}


def train(input_path: Path = DEFAULT_DATA, artifact_path: Path = DEFAULT_ARTIFACT) -> dict[str, Any]:
    features, labels = load_training_data(input_path)
    import pandas as pd

    source = pd.read_csv(input_path)
    counts = labels.value_counts()
    if counts.min() < 2:
        raise ValueError('Each risk class needs at least two rows for a stratified evaluation split')
    label_encoder = LabelEncoder().fit(labels)
    encoded_labels = label_encoder.transform(labels)
    x_train, x_test, y_train, y_test = train_test_split(features, encoded_labels, test_size=0.25, random_state=42, stratify=encoded_labels)
    candidates = build_candidates()
    results: dict[str, Any] = {}
    for name, pipeline in candidates.items():
        pipeline.fit(x_train, y_train)
        predicted = label_encoder.inverse_transform(pipeline.predict(x_test).astype(int))
        expected = label_encoder.inverse_transform(y_test.astype(int))
        metrics = {
            'accuracy': float(accuracy_score(expected, predicted)),
            'precision_weighted': float(precision_score(expected, predicted, average='weighted', zero_division=0)),
            'recall_weighted': float(recall_score(expected, predicted, average='weighted', zero_division=0)),
            'f1_weighted': float(f1_score(expected, predicted, average='weighted', zero_division=0)),
            'labels': label_encoder.classes_.tolist(),
            'confusion_matrix': confusion_matrix(expected, predicted, labels=label_encoder.classes_).tolist(),
        }
        results[name] = metrics
    selected_name = max(results, key=lambda name: results[name]['f1_weighted'])
    selected = candidates[selected_name]
    selected.fit(features, encoded_labels)
    metadata = {
        'model_version': datetime.now(timezone.utc).strftime('risk-%Y%m%dT%H%M%SZ'),
        'selected_model': selected_name,
        'trained_at': datetime.now(timezone.utc).isoformat(),
        'training_rows': int(len(features)),
        'evaluation_rows': int(len(x_test)),
        'features': FEATURES,
        'target': TARGET,
        'class_labels': label_encoder.classes_.tolist(),
        'evaluation': results,
        'dataset': str(input_path.resolve()),
        'demo_data': bool(source.get('data_origin', pd.Series(dtype=str)).eq('DEMO DATA').any()),
    }
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    transformed_background = selected.named_steps['imputer'].transform(features.sample(min(40, len(features)), random_state=42))
    joblib.dump({'pipeline': selected, 'metadata': metadata, 'background': transformed_background, 'label_encoder': label_encoder}, artifact_path)
    artifact_path.with_suffix('.metrics.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description='Train and evaluate the student risk classifier')
    parser.add_argument('--input', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--artifact', type=Path, default=DEFAULT_ARTIFACT)
    args = parser.parse_args()
    result = train(args.input, args.artifact)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()