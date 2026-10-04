import pandas as pd
import pytest
from sklearn.preprocessing import LabelEncoder

from ai.risk.features import FEATURE_CONTRACT, FEATURES, load_training_data
from ai.risk.predict import DEFAULT_ARTIFACT, load_artifact, predict
from ai.risk.train import train
from ai.explainability.service import explain_student
from backend.app.services.momentum import calculate_momentum


def test_momentum_requires_history_and_classifies_trend():
    assert calculate_momentum([82, 78, 71])['classification'] == 'INSUFFICIENT_DATA'
    assert calculate_momentum([82, 78, 71, 63])['classification'] == 'DECLINING'
    assert calculate_momentum([51, 64, 74, 84])['classification'] == 'IMPROVING'
    assert calculate_momentum([69, 70, 69, 70])['classification'] == 'STABLE'
    assert calculate_momentum([45, 90, 42, 92])['classification'] == 'VOLATILE'


def test_training_persists_evaluated_model_and_predicts(tmp_path):
    rows = []
    for index in range(60):
        high = index % 3 == 0
        values = {name: float(index % 7 + 1) for name in FEATURES}
        values.update({
            'attendance': 60 if high else 94,
            'assessment': 48 if high else 86,
            'current_gpa': 2 if high else 3.7,
            'risk_label': 'HIGH' if high else 'LOW',
        })
        rows.append(values)
    source = tmp_path / 'training.csv'
    pd.DataFrame(rows).to_csv(source, index=False)
    model_path = tmp_path / 'risk.joblib'
    metadata = train(source, model_path)
    assert model_path.exists()
    assert model_path.with_suffix('.metrics.json').exists()
    assert metadata['evaluation'][metadata['selected_model']]['f1_weighted'] >= 0.9
    result = predict(rows[0] | {name: value for name, value in rows[0].items() if name in FEATURES}, model_path)
    assert result['risk_level'] in {'LOW', 'MEDIUM', 'HIGH'}
    assert 0 <= result['risk_probability'] <= 1
    assert list(result['class_probabilities']) == list(artifact_classes(model_path))
    assert result['risk_level'] == max(result['class_probabilities'], key=result['class_probabilities'].get)
    assert result['risk_probability'] == result['class_probabilities'][result['risk_level']]
    assert result['risk_probability_semantics'] == 'P(risk_level)'
    assert result['risk_level_policy'] == 'argmax(class_probabilities)'
    assert sum(result['class_probabilities'].values()) == pytest.approx(1.0)
    assert all(0 <= value <= 1 for value in result['class_probabilities'].values())
    explanation = explain_student({name: rows[0][name] for name in FEATURES}, model_path)
    assert explanation['model_version'] == metadata['model_version']
    assert explanation['target_class'] == result['risk_level']
    assert explanation['target'] == f"P({result['risk_level']})"
    assert explanation['base_value'] + sum(explanation['contributions'].values()) == pytest.approx(result['risk_probability'], abs=1e-5)
    assert len(explanation['waterfall']) == len(FEATURES)
    assert explanation['contributions']['attendance'] != 0
    assert all(item['contribution'] == explanation['contributions'][item['feature']] for item in explanation['waterfall'])
    ranked_features = sorted(explanation['contributions'], key=lambda name: abs(explanation['contributions'][name]), reverse=True)
    assert all(item.startswith(name.replace('_', ' ').capitalize()) for item, name in zip(explanation['summary'], ranked_features))


def artifact_classes(model_path):
    import joblib
    import numpy as np

    artifact = joblib.load(model_path)
    return artifact['label_encoder'].inverse_transform(np.asarray(artifact['pipeline'].classes_, dtype=int))


def test_prediction_maps_permuted_classes_and_selects_the_winning_probability(monkeypatch, tmp_path):
    import numpy as np

    class FixedPipeline:
        classes_ = np.asarray([2, 0, 1])

        def predict_proba(self, frame):
            return np.asarray([[0.9949270346416472, 0.0007082902259700415, 0.00436467513238273]])

    artifact = {
        'pipeline': FixedPipeline(),
        'label_encoder': LabelEncoder().fit(['HIGH', 'LOW', 'MEDIUM']),
        'metadata': {'model_version': 'risk-test'},
    }
    monkeypatch.setattr('ai.risk.predict.load_artifact', lambda _: artifact)

    result = predict({name: 0.0 for name in FEATURES}, tmp_path / 'unused.joblib')

    assert result['class_probabilities'] == {
        'MEDIUM': 0.9949270346416472,
        'HIGH': 0.0007082902259700415,
        'LOW': 0.00436467513238273,
    }
    assert result['risk_level'] == 'MEDIUM'
    assert result['risk_probability'] == result['class_probabilities']['MEDIUM']
    assert result['risk_level'] == max(result['class_probabilities'], key=result['class_probabilities'].get)
    assert sum(result['class_probabilities'].values()) == pytest.approx(1.0)
    assert all(0 <= value <= 1 for value in result['class_probabilities'].values())


def test_feature_loader_ignores_identity_and_target_proxy(tmp_path):
    source = tmp_path / 'bad.csv'
    pd.DataFrame([{'student_id': 'S-1', 'risk_probability': 0.9, 'risk_label': 'HIGH'}]).to_csv(source, index=False)
    try:
        load_training_data(source)
    except ValueError as exc:
        assert 'missing required columns' in str(exc)
    else:
        raise AssertionError('incomplete model features must be rejected')


def test_fa_marks_are_documented_context_not_current_model_features():
    artifact = load_artifact(DEFAULT_ARTIFACT)
    assert set(artifact['metadata']['features']) == set(FEATURES)
    assert FEATURE_CONTRACT['fa1']['model_input'] is False
    assert FEATURE_CONTRACT['fa2']['model_input'] is False
    assert FEATURE_CONTRACT['fa1']['scope'] == FEATURE_CONTRACT['fa2']['scope'] == 'subject'


def test_existing_artifact_has_genuine_high_prediction_with_matching_shap_target():
    artifact = load_artifact(DEFAULT_ARTIFACT)
    for row in artifact['background']:
        features = {name: float(value) for name, value in zip(FEATURES, row)}
        prediction = predict(features)
        if prediction['risk_level'] == 'HIGH':
            explanation = explain_student(features, target_class=prediction['risk_level'])
            assert explanation['target_class'] == prediction['risk_level'] == 'HIGH'
            assert explanation['target'] == 'P(HIGH)'
            assert explanation['model_version'] == prediction['model_version']
            assert explanation['base_value'] + sum(explanation['contributions'].values()) == pytest.approx(prediction['class_probabilities']['HIGH'], abs=1e-5)
            return
    pytest.fail('The bundled model artifact did not predict HIGH for any persisted background record.')