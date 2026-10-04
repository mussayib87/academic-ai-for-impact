import hashlib
import pickle
from pathlib import Path
from typing import Any

import joblib
from sqlalchemy.orm import Session

from ai.risk.features import FEATURE_CONTRACT_VERSION, FEATURES
from backend.app.models import ModelDeploymentState, ModelRegistryEntry


class DeploymentArtifactError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_artifact_path(entry: ModelRegistryEntry, candidate_directory: Path) -> Path:
    root = candidate_directory.resolve()
    path = (root / (entry.artifact_identifier or '')).resolve()
    if not entry.artifact_identifier or root not in path.parents or not path.is_file():
        raise DeploymentArtifactError('Candidate artifact is missing or outside the local candidate artifact directory.')
    try:
        actual_hash = sha256_file(path)
    except OSError as exc:
        raise DeploymentArtifactError('Candidate artifact cannot be read for SHA-256 verification.') from exc
    if not entry.artifact_hash or actual_hash.casefold() != entry.artifact_hash.casefold():
        raise DeploymentArtifactError('Candidate artifact SHA-256 does not match registry metadata.')
    return path


def verify_candidate_artifact(
    entry: ModelRegistryEntry,
    candidate_directory: Path,
    *,
    production_features: list[str] | None = None,
) -> tuple[Path, dict[str, Any]]:
    path = candidate_artifact_path(entry, candidate_directory)
    try:
        artifact = joblib.load(path)
    except (OSError, EOFError, ImportError, AttributeError, KeyError, TypeError, ValueError, pickle.UnpicklingError) as exc:
        raise DeploymentArtifactError(f'Candidate artifact cannot be loaded safely: {type(exc).__name__}.') from exc
    if not isinstance(artifact, dict):
        raise DeploymentArtifactError('Candidate artifact must be a pipeline metadata bundle.')
    metadata = artifact.get('metadata')
    contract = artifact.get('feature_contract')
    pipeline = artifact.get('pipeline')
    encoder = artifact.get('label_encoder')
    if not isinstance(metadata, dict) or not isinstance(contract, list) or pipeline is None or encoder is None:
        raise DeploymentArtifactError('Candidate artifact is missing its pipeline, label encoder, metadata, or feature contract.')
    if metadata.get('model_version') != entry.model_version:
        raise DeploymentArtifactError('Candidate artifact model version does not match the registry entry.')
    if metadata.get('dataset_fingerprint') != entry.dataset_fingerprint:
        raise DeploymentArtifactError('Candidate artifact dataset fingerprint does not match the registry entry.')
    if contract != entry.feature_schema or metadata.get('feature_contract') != entry.feature_schema:
        raise DeploymentArtifactError('Candidate artifact feature contract does not match registry metadata.')
    if not entry.feature_contract_version or metadata.get('feature_contract_version') != entry.feature_contract_version:
        raise DeploymentArtifactError('Candidate artifact feature-contract version does not match registry metadata.')
    if entry.feature_contract_version != FEATURE_CONTRACT_VERSION:
        raise DeploymentArtifactError('Candidate feature-contract version is incompatible with the live prediction contract.')
    expected_features = production_features or list(FEATURES)
    if contract != expected_features:
        raise DeploymentArtifactError('Candidate feature contract is incompatible with the live prediction input contract.')
    pipeline_features = getattr(pipeline, 'feature_names_in_', None)
    if pipeline_features is not None and list(pipeline_features) != contract:
        raise DeploymentArtifactError('Candidate pipeline feature order is incompatible with its registered feature contract.')
    if getattr(pipeline, 'n_features_in_', len(contract)) != len(contract):
        raise DeploymentArtifactError('Candidate pipeline input width is incompatible with its feature contract.')
    if not callable(getattr(pipeline, 'predict_proba', None)):
        raise DeploymentArtifactError('Candidate pipeline does not expose class probabilities required by risk inference.')
    labels = getattr(encoder, 'classes_', None)
    model_classes = getattr(pipeline, 'classes_', None)
    if labels is None or set(map(str, labels)) != {'HIGH', 'MEDIUM', 'LOW'}:
        raise DeploymentArtifactError('Candidate label encoder is incompatible with the supported risk classes.')
    try:
        class_ids = sorted(map(int, model_classes)) if model_classes is not None else []
    except (TypeError, ValueError) as exc:
        raise DeploymentArtifactError('Candidate classifier classes are incompatible with its label encoder.') from exc
    if len(class_ids) != 3 or class_ids != [0, 1, 2]:
        raise DeploymentArtifactError('Candidate classifier classes are incompatible with its label encoder.')
    metrics = entry.validation_metrics
    if not isinstance(metrics, dict) or not all(key in metrics for key in ('validation', 'test')):
        raise DeploymentArtifactError('Candidate validation and test evaluation references are incomplete.')
    artifact_metrics = {
        'validation': metadata.get('validation_metrics'),
        'test': metadata.get('test_metrics'),
        'feature_importance': metadata.get('feature_importance'),
        'subgroup_evaluation': metadata.get('subgroup_evaluation'),
    }
    if any(metrics.get(key) != value for key, value in artifact_metrics.items()):
        raise DeploymentArtifactError('Candidate evaluation metadata does not match the registry evaluation reference.')
    if not metadata.get('dataset_id') or not metadata.get('target_definition') or not metadata.get('aggregation_strategy'):
        raise DeploymentArtifactError('Candidate dataset and target provenance metadata is incomplete.')
    if entry.training_dataset_hash != entry.dataset_fingerprint:
        raise DeploymentArtifactError('Registry training dataset hash does not match the candidate dataset fingerprint.')
    if entry.algorithm != 'logistic_regression' or metadata.get('algorithm') != entry.algorithm:
        raise DeploymentArtifactError('Candidate algorithm metadata is incompatible with the supported local inference adapter.')
    return path, artifact


def active_artifact_path(
    db: Session,
    *,
    candidate_directory: Path,
    production_path: Path,
    production_version: str,
    production_hash: str,
) -> Path:
    state = db.query(ModelDeploymentState).filter(ModelDeploymentState.id == 1).first()
    if state is None or state.active_model_version == production_version:
        if state is not None and state.active_artifact_hash.casefold() != production_hash.casefold():
            raise DeploymentArtifactError('Active local production artifact hash no longer matches deployment state.')
        try:
            production_matches = production_path.is_file() and sha256_file(production_path).casefold() == production_hash.casefold()
        except OSError as exc:
            raise DeploymentArtifactError('Fallback production artifact cannot be read for SHA-256 verification.') from exc
        if not production_matches:
            raise DeploymentArtifactError('Fallback production artifact is unavailable or has changed unexpectedly.')
        return production_path
    entry = db.query(ModelRegistryEntry).filter(ModelRegistryEntry.model_version == state.active_model_version).first()
    if entry is None:
        raise DeploymentArtifactError('The active local model version has no registry entry; refusing to fall back silently.')
    if entry.status != 'candidate' or entry.deployment_status != 'LOCAL_ACTIVE':
        raise DeploymentArtifactError('The selected registry version is not an active local candidate.')
    if entry.validation_status != 'passed' or entry.approval_status != 'approved':
        raise DeploymentArtifactError('The selected local candidate no longer satisfies validation and approval state.')
    if state.active_artifact_hash.casefold() != (entry.artifact_hash or '').casefold():
        raise DeploymentArtifactError('Active deployment state artifact hash differs from registry metadata.')
    path, _ = verify_candidate_artifact(entry, candidate_directory)
    return path
