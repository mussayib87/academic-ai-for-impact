import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from ai.llm.grounding import validate_intervention_draft
from ai.llm.provider import DevelopmentDraftProvider, GeminiProvider, InterventionContext, LocalLLMProvider, build_provider
from ai.rag.index import index_documents, read_source, retrieve, split_text


def test_retrieval_finds_source_and_reports_provider(tmp_path):
    corpus = tmp_path / 'knowledge'
    corpus.mkdir()
    (corpus / 'mentoring.md').write_text('Faculty mentoring sessions are available by appointment for study planning.', encoding='utf-8')
    index_path = tmp_path / 'vector' / 'index.joblib'
    indexed = index_documents(corpus, index_path)
    result = retrieve('mentoring sessions and study planning', store_path=index_path)
    assert indexed['documents'] == 1
    assert result['matched'] is True
    assert result['sources'][0]['source'] == 'mentoring.md'
    assert 'development-fallback' in result['embedding_provider']


def test_no_matching_source_is_explicit(tmp_path):
    corpus = tmp_path / 'knowledge'
    corpus.mkdir()
    (corpus / 'support.txt').write_text('Tutoring support is available.', encoding='utf-8')
    index_path = tmp_path / 'index.joblib'
    index_documents(corpus, index_path)
    result = retrieve('international tax law', store_path=index_path)
    assert result['matched'] is False
    assert 'no policy has been inferred' in result['message']


def test_missing_index_explicitly_reports_no_institutional_policy(tmp_path):
    result = retrieve('academic policy', store_path=tmp_path / 'missing.joblib')
    assert result['matched'] is False
    assert result['sources'] == []
    assert 'No institutional policy has been inferred' in result['message']


def test_approved_docx_source_is_extractable_and_indexable(tmp_path):
    corpus = tmp_path / 'knowledge'
    corpus.mkdir()
    source = corpus / 'approved-guide.docx'
    document = Document()
    document.add_paragraph('Approved study planning resource for faculty mentoring.')
    document.save(source)
    assert 'Approved study planning resource' in read_source(source)
    index_path = tmp_path / 'index.joblib'
    result = index_documents(corpus, index_path)
    assert result['documents'] == 1
    assert retrieve('faculty mentoring study planning', store_path=index_path)['sources'][0]['source'] == 'approved-guide.docx'


def test_pdf_source_extraction_is_supported(tmp_path, monkeypatch):
    import pypdf

    class Page:
        @staticmethod
        def extract_text():
            return 'Approved academic support resource.'

    class Reader:
        def __init__(self, path):
            self.pages = [Page()]

    source = tmp_path / 'approved.pdf'
    source.write_bytes(b'%PDF-test')
    monkeypatch.setattr(pypdf, 'PdfReader', Reader)
    assert read_source(source) == 'Approved academic support resource.'


def _pdf_with_text(text: str) -> bytes:
    stream = f'BT /F1 12 Tf 72 720 Td ({text}) Tj ET'.encode('ascii')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode('ascii') + b' >>\nstream\n' + stream + b'\nendstream',
    ]
    pdf = bytearray(b'%PDF-1.4\n')
    offsets = []
    for index, item in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f'{index} 0 obj\n'.encode('ascii'))
        pdf.extend(item)
        pdf.extend(b'\nendobj\n')
    xref_offset = len(pdf)
    pdf.extend(f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode('ascii'))
    for offset in offsets:
        pdf.extend(f'{offset:010} 00000 n \n'.encode('ascii'))
    pdf.extend(f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n'.encode('ascii'))
    return bytes(pdf)


def test_pdf_is_indexed_and_retrievable_without_inferred_policy(tmp_path, monkeypatch):
    import ai.rag.index as rag_index

    corpus = tmp_path / 'approved-sources'
    corpus.mkdir()
    text = 'Quasar calibration spectra are stored in archive seventeen.'
    (corpus / 'quasar-observations.pdf').write_bytes(_pdf_with_text(text))
    monkeypatch.setattr(rag_index, 'get_settings', lambda: SimpleNamespace(embedding_model_name='hashing-pdf-test'))

    index_path = tmp_path / 'pdf-index.joblib'
    indexed = index_documents(corpus, index_path)
    result = retrieve('quasar calibration spectra', store_path=index_path)

    assert indexed['documents'] == 1
    assert indexed['chunks'] == 1
    assert result['matched'] is True
    assert result['sources'][0]['source'] == 'quasar-observations.pdf'
    assert text in result['sources'][0]['text']
    assert result['sources'][0]['text'] == text
    assert 'policy' not in result['sources'][0]['text'].lower()


def test_development_draft_is_not_misrepresented_as_llm():
    context = InterventionContext(student_name='Alex', risk_level='MEDIUM', risk_probability=0.55, attendance=72, assessment=61, assignment_engagement=0.5)
    draft = DevelopmentDraftProvider().generate_intervention(context)
    assert draft.startswith('AI-GENERATED DRAFT - FACULTY REVIEW REQUIRED')
    assert 'not generated by a language model' in draft


def test_ollama_configuration_uses_canonical_model_and_base_url():
    provider = LocalLLMProvider('ollama:qwen3:8b', base_url='http://127.0.0.1:11434', timeout_seconds=180)
    assert provider.base_url == 'http://127.0.0.1:11434'
    assert provider.model_name == 'qwen3:8b'
    assert provider.provider_name == 'ollama-local'


def test_ollama_health_check_reports_unreachable_service(monkeypatch):
    def fake_urlopen(request, timeout):
        raise OSError('Connection refused')

    monkeypatch.setattr('ai.llm.provider.urlopen', fake_urlopen)
    provider = LocalLLMProvider('ollama:qwen3:8b', base_url='http://127.0.0.1:11434', timeout_seconds=8)

    status = provider.get_health_status()

    assert status['provider'] == 'ollama-local'
    assert status['base_url'] == 'http://127.0.0.1:11434'
    assert status['model'] == 'qwen3:8b'
    assert status['reachable'] is False
    assert status['model_available'] is False
    assert 'not reachable' in status['error'].lower()


def test_local_llm_uses_configured_request_timeout(monkeypatch):
    request_timeouts = []
    responses = iter([
        b'{"models":[{"name":"qwen3:8b"}]}',
        b'{"response":"A supportive check-in."}',
    ])

    def fake_urlopen(request, timeout):
        request_timeouts.append(timeout)
        return BytesIO(next(responses))

    monkeypatch.setattr('ai.llm.provider.urlopen', fake_urlopen)
    context = InterventionContext(student_name='Alex', risk_level='MEDIUM', risk_probability=0.55, attendance=72, assessment=61, assignment_engagement=0.5)

    provider = LocalLLMProvider('ollama:qwen3:8b', timeout_seconds=137)
    draft = provider.generate_intervention(context)

    assert request_timeouts == [10, 137]
    assert provider.provider_name == 'ollama-local'
    assert draft.endswith('A supportive check-in.')


def test_gemini_uses_structured_evidence_and_requires_review(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured['request'] = request
        captured['timeout'] = timeout
        return BytesIO(b'{"candidates":[{"content":{"parts":[{"text":"Subject: Check-in\\nLet us discuss a next step."}]}}]}')

    monkeypatch.setattr('ai.llm.provider.urlopen', fake_urlopen)
    context = InterventionContext(
        student_name='Alex', risk_level='HIGH', risk_probability=0.86,
        shap_factors=['Attendance reduced P(HIGH)'], momentum={'assessment': 'DECLINING'},
        attendance=62, assessment=54, assignment_engagement=0.5,
        institutional_resources=[{'title': 'Approved guide', 'text': 'Study planning resource.'}],
    )
    provider = GeminiProvider('test-key', 'gemini-test', timeout_seconds=41)
    draft = provider.generate_intervention(context)
    request_body = json.loads(captured['request'].data)
    prompt = request_body['contents'][0]['parts'][0]['text']
    assert captured['timeout'] == 41
    assert captured['request'].get_header('X-goog-api-key') == 'test-key'
    assert all(value in prompt for value in ('risk_probability', 'class_probabilities', 'model_version', 'shap_factors', 'momentum', 'attendance', 'assessment', 'assignment_engagement', 'institutional_resources'))
    assert all(value in prompt.lower() for value in ('do not diagnose', 'do not invent institutional policy', 'unsupported claims', 'automatic action', 'faculty review'))
    assert draft.startswith('AI-GENERATED DRAFT - FACULTY REVIEW REQUIRED')
    assert provider.provider_name == 'gemini'


def test_provider_selection_keeps_ollama_available_when_gemini_key_is_missing():
    class Settings:
        selected_llm_provider = 'gemini'
        gemini_api_key = ''
        gemini_model_name = 'gemini-test'
        llm_timeout_seconds = 10
        llm_model_name = 'ollama:qwen3:8b'

    provider = build_provider(Settings())
    assert isinstance(provider, LocalLLMProvider)
    assert provider.model_name == 'qwen3:8b'


def test_text_chunking_overlaps_long_documents():
    chunks = split_text('a' * 2500)
    assert len(chunks) == 3
    assert chunks[0][-100:] == chunks[1][:100]


def _stable_evidence_context():
    return InterventionContext(
        student_name='Alex',
        risk_level='MEDIUM',
        risk_probability=0.6,
        class_probabilities={'HIGH': 0.1, 'MEDIUM': 0.6, 'LOW': 0.3},
        momentum={'attendance': 'STABLE', 'assessment': 'STABLE'},
        attendance=76,
        assessment=68,
        assignment_engagement=0.7,
        source_notice='No verified institutional resource is currently configured.',
    )


def _draft_with_claim(claim):
    return (
        'AI-GENERATED DRAFT - FACULTY REVIEW REQUIRED\n'
        'OBSERVATIONS:\nCurrent risk is MEDIUM (0.6). Attendance momentum is STABLE. '
        'Assessment momentum is STABLE. No verified institutional resource is currently configured.\n'
        f'{claim}\n'
        'RECOMMENDATIONS:\nConsider discussing assignment planning with the student.'
    )


@pytest.mark.parametrize(('claim', 'expected_issue'), [
    ('There are ongoing fluctuations in attendance and assessment.', 'Unsupported attendance momentum claim'),
    ('The student has sustained risk.', 'Unsupported temporal claim'),
    ('Persistent fluctuations in attendance were observed.', 'Unsupported temporal claim'),
    ('Assignments reduced risk.', 'Unsupported causal relationship'),
])
def test_grounding_validator_rejects_observed_qwen_claims(claim, expected_issue):
    errors = validate_intervention_draft(_draft_with_claim(claim), _stable_evidence_context())

    assert any(expected_issue in error for error in errors)


def test_grounding_validator_accepts_facts_and_separate_recommendations():
    errors = validate_intervention_draft(_draft_with_claim('Assignment engagement is 0.7.'), _stable_evidence_context())

    assert errors == []


def test_grounding_validator_requires_faculty_review_framing():
    body = _draft_with_claim('Assignment engagement is 0.7.').removeprefix(
        'AI-GENERATED DRAFT - FACULTY REVIEW REQUIRED\n'
    )

    errors = validate_intervention_draft(body, _stable_evidence_context())

    assert 'Missing required faculty-review draft framing.' in errors


def test_grounding_validator_rejects_conflicting_stable_momentum():
    body = _draft_with_claim('Attendance is declining.')

    errors = validate_intervention_draft(body, _stable_evidence_context())

    assert any('attendance momentum' in error for error in errors)


def test_grounding_validator_allows_neutral_recommendation_with_temporal_word():
    body = _draft_with_claim('') + '\nConsider arranging ongoing check-ins with faculty.'

    errors = validate_intervention_draft(body, _stable_evidence_context())

    assert errors == []


def test_grounding_validator_rejects_invented_institutional_resource():
    body = _draft_with_claim('Contact the Academic Success Center for tutoring.')

    errors = validate_intervention_draft(body, _stable_evidence_context())

    assert any('unverified institutional resource' in error for error in errors)


def test_grounding_validator_rejects_captured_qwen3_unsupported_output():
    context = InterventionContext(
        student_name='Demo Student 001',
        risk_level='MEDIUM',
        risk_probability=0.9949270346416472,
        momentum={
            'attendance': 'STABLE',
            'assessment': 'STABLE',
            'activity': 'VOLATILE',
            'assignment_submission': 'VOLATILE',
        },
        attendance=87.4,
        assessment=65.7,
        assignment_engagement=2.0,
        shap_evidence=[
            {'feature': 'assessment', 'value': 65.7, 'model_contribution': 0.333},
            {'feature': 'attendance', 'value': 87.4, 'model_contribution': 0.117},
            {'feature': 'assignments_completed', 'value': 2.0, 'model_contribution': -0.0012},
        ],
        source_notice='No verified institutional resource is currently configured.',
    )
    body = '''AI-GENERATED DRAFT - FACULTY REVIEW REQUIRED
OBSERVATIONS:
- Student risk level has sustained medium risk (probability: 99.49%).
- Attendance: 87.4% with STABLE momentum.
- Assessment score: 65.7 with STABLE momentum.
- Assignment engagement: 2.0 with VOLATILE momentum.
- Recent volatility in activity engagement and assignment submissions suggests targeted support.
- Ongoing fluctuations in attendance and assessment momentum warrant a check-in.
- No verified institutional resource is currently configured.
RECOMMENDATIONS:
- Offer support to address assessment gaps.
- Reinforce attendance expectations and acknowledge the stable attendance trend as a positive sign.
- SHAP model contributions show assessment and attendance as key contributors to risk level.
- Assignments completed slightly reduced predicted risk.'''

    errors = validate_intervention_draft(body, context)

    assert any('attendance momentum' in error for error in errors)
    assert any('temporal claim' in error for error in errors)
    assert any('assessment gaps' in error for error in errors)
    assert any('SHAP contributions' in error for error in errors)
    assert any('causal relationship' in error for error in errors)