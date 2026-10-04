import hashlib
import json
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder

from ai.risk.phase3 import OUTCOME_CLASSES, temporal_split


FORBIDDEN_FEATURES = {
    'student_id', 'student_identifier', 'risk_target', 'risk_level', 'risk_probability',
    'risk_observed_at', 'outcome_source', 'academic_period', 'subject_code',
}


def _package_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _metrics(expected: np.ndarray, predicted: np.ndarray, probabilities: np.ndarray, labels: list[str]) -> dict[str, Any]:
    support = np.bincount(expected, minlength=len(labels))
    precision, recall, f1, _ = precision_recall_fscore_support(
        expected, predicted, labels=np.arange(len(labels)), zero_division=0,
    )
    per_class = {
        label: {
            'precision': float(precision[index]) if support[index] else None,
            'recall': float(recall[index]) if support[index] else None,
            'f1': float(f1[index]) if support[index] else None,
            'support': int(support[index]),
        }
        for index, label in enumerate(labels)
    }
    one_hot = np.eye(len(labels), dtype=float)[expected]
    try:
        roc_auc = float(roc_auc_score(expected, probabilities, labels=np.arange(len(labels)), multi_class='ovr', average='macro')) if len(np.unique(expected)) == len(labels) else None
    except ValueError:
        roc_auc = None
    try:
        pr_auc = float(average_precision_score(one_hot, probabilities, average='macro')) if len(np.unique(expected)) == len(labels) else None
    except ValueError:
        pr_auc = None
    predicted_confidence = np.max(probabilities, axis=1)
    predicted_class = np.argmax(probabilities, axis=1)
    ece = 0.0
    for lower in np.linspace(0, 0.9, 10):
        upper = lower + 0.1
        mask = (predicted_confidence >= lower) & (predicted_confidence < upper if upper < 1 else predicted_confidence <= 1)
        if mask.any():
            accuracy = np.mean(expected[mask] == predicted_class[mask])
            confidence = np.mean(predicted_confidence[mask])
            ece += float(mask.mean() * abs(accuracy - confidence))
    return {
        'sample_count': int(len(expected)),
        'class_distribution': {label: int(support[index]) for index, label in enumerate(labels)},
        'accuracy': float(accuracy_score(expected, predicted)),
        'macro_f1': float(f1_score(expected, predicted, labels=np.unique(expected), average='macro', zero_division=0)),
        'weighted_f1': float(f1_score(expected, predicted, labels=np.arange(len(labels)), average='weighted', zero_division=0)),
        'balanced_accuracy': float(balanced_accuracy_score(expected, predicted)),
        'per_class': per_class,
        'confusion_matrix': confusion_matrix(expected, predicted, labels=np.arange(len(labels))).tolist(),
        'labels': labels,
        'roc_auc_ovr_macro': roc_auc,
        'pr_auc_ovr_macro': pr_auc,
        'multiclass_brier_score': float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        'expected_calibration_error_10_bins': ece,
    }


def _subgroup_evaluation(
    frame: pd.DataFrame,
    expected: np.ndarray,
    predicted: np.ndarray,
    probabilities: np.ndarray,
    labels: list[str],
    *,
    min_samples: int = 20,
) -> dict[str, Any]:
    evaluated: dict[str, dict[str, Any]] = {}
    withheld: dict[str, dict[str, int]] = {}
    candidate_groups = ('academic_period', 'subject_or_aggregation', 'department', 'section')
    for column in candidate_groups:
        if column not in frame:
            continue
        evaluated[column] = {}
        withheld[column] = {}
        if frame[column].isna().all():
            withheld[column]['UNSPECIFIED'] = int(len(frame))
            continue
        values = frame[column].fillna('UNSPECIFIED').astype(str)
        for value in sorted(values.unique()):
            mask = values.to_numpy() == value
            sample_count = int(mask.sum())
            if value == 'UNSPECIFIED' or sample_count < min_samples:
                withheld[column][value] = sample_count
                continue
            metrics = _metrics(expected[mask], predicted[mask], probabilities[mask], labels)
            evaluated[column][value] = metrics
    return {
        'minimum_sample_count': min_samples,
        'split': 'test',
        'evaluated': {name: values for name, values in evaluated.items() if values},
        'withheld_for_insufficient_sample': {name: values for name, values in withheld.items() if values},
        'interpretation': 'Descriptive held-out subgroup performance only; no fairness or causal claim is made.',
    }


def train_candidate(
    frame: pd.DataFrame,
    *,
    output_directory: Path,
    feature_contract: list[str],
    target_column: str,
    period_column: str,
    identity_column: str,
    dataset_id: str,
    dataset_version: str,
    dataset_fingerprint: str,
    target_definition: str,
    aggregation_strategy: str,
    random_seed: int = 42,
    algorithm: str = 'logistic_regression',
) -> dict[str, Any]:
    if not feature_contract or len(feature_contract) != len(set(feature_contract)):
        raise ValueError('An explicit, non-empty feature contract is required.')
    if any(name.casefold() in FORBIDDEN_FEATURES for name in feature_contract):
        raise ValueError('The feature contract contains identity, target, or grouping leakage fields.')
    if not target_definition.strip() or not aggregation_strategy.strip():
        raise ValueError('An explicit target definition and aggregation strategy are required.')
    if algorithm != 'logistic_regression':
        raise ValueError('Unsupported candidate algorithm; currently only logistic_regression is implemented.')
    if len(dataset_fingerprint) != 64 or any(character not in '0123456789abcdef' for character in dataset_fingerprint.casefold()):
        raise ValueError('dataset_fingerprint must be a SHA-256 hexadecimal string.')
    required = {*feature_contract, target_column, period_column, identity_column}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f'Candidate dataset is missing required columns: {", ".join(missing)}')
    if frame.empty:
        raise ValueError('Candidate dataset contains no eligible observations.')
    if frame[[identity_column, period_column]].duplicated().any():
        raise ValueError('Duplicate student-period rows are not allowed; explicitly aggregate subject observations first.')
    if frame[target_column].isna().any():
        raise ValueError('Candidate dataset contains missing targets.')
    periods = sorted(frame[period_column].astype(str).unique().tolist())
    split = temporal_split(periods)
    masks = {
        'training': frame[period_column].astype(str).isin(split['training_periods']),
        'validation': frame[period_column].astype(str).isin(split['validation_periods']),
        'test': frame[period_column].astype(str).isin(split['test_periods']),
    }
    if any(not mask.any() for mask in masks.values()):
        raise ValueError('Temporal train, validation, and test splits must each contain observations.')
    features = frame[feature_contract].apply(pd.to_numeric, errors='coerce')
    if features.isna().all(axis=0).any():
        empty_columns = features.columns[features.isna().all(axis=0)].tolist()
        raise ValueError(f'Candidate feature(s) have no training observations: {", ".join(empty_columns)}')
    labels = frame[target_column].astype(str).str.upper()
    if not set(labels.unique()) <= set(OUTCOME_CLASSES):
        raise ValueError('Candidate target contains an unsupported risk class.')
    training_labels = labels[masks['training']]
    encoder = LabelEncoder().fit(training_labels)
    try:
        encoded = {name: encoder.transform(labels[mask]) for name, mask in masks.items()}
    except ValueError as exc:
        raise ValueError('A validation or test period contains a class absent from earlier training periods.') from exc
    if len(encoder.classes_) < 2:
        raise ValueError('Temporal training observations must contain at least two risk classes.')
    label_names = encoder.classes_.tolist()

    pipeline = Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('classifier', LogisticRegression(max_iter=2000, class_weight='balanced', random_state=random_seed)),
    ])
    pipeline.fit(features.loc[masks['training'], feature_contract], encoded['training'])
    split_metrics: dict[str, dict[str, Any]] = {}
    split_predictions: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for name in ('validation', 'test'):
        split_features = features.loc[masks[name], feature_contract]
        expected = encoded[name]
        predicted = pipeline.predict(split_features).astype(int)
        probabilities = pipeline.predict_proba(split_features)
        split_metrics[name] = _metrics(expected, predicted, probabilities, label_names)
        split_predictions[name] = (predicted, probabilities)

    trained_at = datetime.now(timezone.utc).isoformat()
    model_version = f'candidate-{dataset_fingerprint[:12]}-{algorithm}-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}'
    classifier = pipeline.named_steps['classifier']
    validation_features = features.loc[masks['validation'], feature_contract]
    permutation = permutation_importance(
        pipeline,
        validation_features,
        encoded['validation'],
        scoring='f1_macro',
        n_repeats=10,
        random_state=random_seed,
    )
    feature_importance = {
        'method': 'validation-period permutation importance; scoring=macro_f1',
        'split': 'validation',
        'sample_count': int(len(validation_features)),
        'features': {
            name: {'mean': float(mean), 'std': float(std)}
            for name, mean, std in zip(feature_contract, permutation.importances_mean, permutation.importances_std)
        },
    }
    test_predicted, test_probabilities = split_predictions['test']
    subgroup_evaluation = _subgroup_evaluation(
        frame.loc[masks['test']].reset_index(drop=True),
        encoded['test'],
        test_predicted,
        test_probabilities,
        label_names,
    )
    metadata: dict[str, Any] = {
        'model_version': model_version,
        'dataset_id': dataset_id,
        'dataset_version': dataset_version,
        'dataset_fingerprint': dataset_fingerprint,
        'feature_contract': feature_contract,
        'feature_contract_version': 'phase3-candidate-explicit-v1',
        'target_definition': target_definition,
        'aggregation_strategy': aggregation_strategy,
        'training_periods': split['training_periods'],
        'validation_periods': split['validation_periods'],
        'test_periods': split['test_periods'],
        'algorithm': algorithm,
        'hyperparameters': {'max_iter': 2000, 'class_weight': 'balanced', 'random_state': random_seed},
        'random_seed': random_seed,
        'training_timestamp': trained_at,
        'software_versions': {
            'python': '.'.join(map(str, __import__('sys').version_info[:3])),
            'scikit_learn': _package_version('scikit-learn'),
            'numpy': _package_version('numpy'),
            'pandas': _package_version('pandas'),
            'shap': _package_version('shap'),
        },
        'sample_counts': {name: int(mask.sum()) for name, mask in masks.items()},
        'class_distribution': {label: int((training_labels == label).sum()) for label in label_names},
        'validation_metrics': split_metrics['validation'],
        'test_metrics': split_metrics['test'],
        'feature_importance': feature_importance,
        'subgroup_evaluation': subgroup_evaluation,
        'shap_metadata': {'method': 'permutation SHAP on candidate pipeline class probability', 'generated': False},
        'status': 'candidate',
    }
    output_directory = Path(output_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    artifact_path = output_directory / f'{model_version}.joblib'
    background = features.loc[masks['training'], feature_contract].sample(min(40, int(masks['training'].sum())), random_state=random_seed).to_numpy(dtype=float)
    joblib.dump({
        'pipeline': pipeline,
        'label_encoder': encoder,
        'metadata': metadata,
        'feature_contract': feature_contract,
        'background': background,
    }, artifact_path)
    artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    metadata['artifact_identifier'] = artifact_path.name
    metadata['artifact_hash'] = artifact_hash
    artifact_path.with_suffix('.metrics.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    return {'artifact_path': artifact_path, 'artifact_hash': artifact_hash, 'metadata': metadata}


def explain_candidate(artifact_path: Path, feature_values: dict[str, float], *, target_class: str | None = None) -> dict[str, Any]:
    artifact = joblib.load(artifact_path)
    contract = artifact['feature_contract']
    missing = sorted(set(contract) - set(feature_values))
    extra = sorted(set(feature_values) - set(contract))
    if missing or extra:
        raise ValueError(f'Candidate SHAP input contract mismatch; missing={missing}, unsupported={extra}')
    frame = pd.DataFrame([{name: float(feature_values[name]) for name in contract}], columns=contract)
    pipeline = artifact['pipeline']
    encoder: LabelEncoder = artifact['label_encoder']
    labels = encoder.classes_.tolist()
    probabilities = pipeline.predict_proba(frame)[0]
    target = target_class.upper() if target_class else labels[int(np.argmax(probabilities))]
    if target not in labels:
        raise ValueError(f'Unknown candidate SHAP target class: {target}')
    target_index = labels.index(target)
    background = np.asarray(artifact['background'], dtype=float)

    def class_probability(values: np.ndarray) -> np.ndarray:
        candidate_frame = pd.DataFrame(values, columns=contract)
        return pipeline.predict_proba(candidate_frame)[:, target_index]

    explainer = shap.Explainer(class_probability, background, feature_names=contract, algorithm='permutation')
    explanation = explainer(frame.to_numpy(dtype=float), max_evals=2 * len(contract) + 1)
    contributions = np.asarray(explanation.values)[0]
    base_value = float(np.asarray(explanation.base_values).reshape(-1)[0])
    probability = float(probabilities[target_index])
    reconstruction = base_value + float(np.sum(contributions))
    if not np.isclose(reconstruction, probability, atol=1e-4):
        raise ValueError('Candidate SHAP values failed the probability additivity check.')
    contribution_map = {name: float(value) for name, value in zip(contract, contributions)}
    ranked = sorted(contribution_map.items(), key=lambda item: abs(item[1]), reverse=True)
    return {
        'model_version': artifact['metadata']['model_version'],
        'target': f'P({target})',
        'target_class': target,
        'probability': probability,
        'base_value': base_value,
        'contributions': contribution_map,
        'feature_values': {name: float(frame.iloc[0][name]) for name in contract},
        'summary': [
            f'{name.replace("_", " ").capitalize()} increased the candidate P({target}).' if value > 0
            else f'{name.replace("_", " ").capitalize()} reduced the candidate P({target}).'
            for name, value in ranked[:5]
        ],
        'waterfall': [{'feature': name, 'value': float(frame.iloc[0][name]), 'contribution': value} for name, value in ranked],
        'additivity_error': reconstruction - probability,
        'shap_method': 'permutation',
    }
