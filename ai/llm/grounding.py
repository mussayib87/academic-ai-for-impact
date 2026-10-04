import json
import math
import re
from typing import Any


_REVIEW_HEADER = 'AI-GENERATED DRAFT - FACULTY REVIEW REQUIRED'
_TREND = r'fluctuat\w*|volatil\w*|declin\w*|improv\w*|worsen\w*|increas\w*|decreas\w*|escalat\w*|deteriorat\w*|unstable|drop\w*|fell|falling|risen|rose'
_CAUSAL = r'caus\w*|lead\w* to|result\w* in|reduc\w*|increas\w*|lower\w*|rais\w*|improv\w*|worsen\w*|because|due to|as a result of|driven by'
_TEMPORAL = r'sustained|persistent|worsening|escalating|ongoing|continued|continuing|recent|longstanding|repeated|remains'
_MOMENTUM_DESCRIPTORS = {
    'VOLATILE': r'fluctuat\w*|volatil\w*|unstable',
    'IMPROVING': r'improv\w*|increas\w*|risen|rose|rising|better|gain\w*',
    'DECLINING': r'declin\w*|worsen\w*|decreas\w*|drop\w*|fell|falling|lower\w*',
    'STABLE': r'stable|unchanged|consistent|steady',
}


def build_intervention_prompt(context: Any) -> str:
    momentum = {str(key).lower(): str(value).upper() for key, value in context.momentum.items()}
    facts = {
        'risk': {
            'current_level': context.risk_level,
            'risk_probability': context.risk_probability,
            'probability_semantics': 'P(risk_level)',
            'class_probabilities': context.class_probabilities,
            'model_version': context.model_version,
        },
        'attendance': {
            'current_value_percent': context.attendance,
            'momentum': momentum.get('attendance', 'NOT SUPPORTED'),
        },
        'assessment': {
            'current_value': context.assessment,
            'momentum': momentum.get('assessment', 'NOT SUPPORTED'),
        },
        'assignments': {
            'assignment_engagement': context.assignment_engagement,
            'momentum': momentum.get('assignment_submission', momentum.get('assignments', 'NOT SUPPORTED')),
        },
        'other_verified_momentum': momentum,
        'shap_factors': context.shap_evidence,
        'shap_model_contributions': context.shap_evidence,
        'temporal_evidence': context.temporal_evidence,
        'causal_evidence': context.causal_evidence,
        'subject_academic_context': context.subject_academic_context,
        'rag': {
            'matched': bool(context.institutional_resources),
            'institutional_resources': context.institutional_resources,
            'verified_resources': context.institutional_resources,
            'source_notice': context.source_notice,
        },
    }
    return (
        'Draft a concise, supportive faculty intervention. This is a draft only.\n\n'
        'OBSERVED FACTS\n'
        'The JSON below is the complete verified evidence contract. A fact may be stated as observed only '
        'when explicitly present in this JSON. Preserve categorical values exactly; do not translate a '
        'momentum class into a different trend description. SHAP entries are model contributions, not causes.\n'
        'VERIFIED STUDENT EVIDENCE\n'
        f'{json.dumps(facts, indent=2, ensure_ascii=False, default=str)}\n\n'
        'RECOMMENDED ACTIONS\n'
        'You may propose practical, non-clinical steps for faculty/student discussion. Label them as '
        'recommendations, not as observed facts or guaranteed outcomes.\n\n'
        'UNKNOWN / NOT SUPPORTED\n'
        'Unless explicitly stated in VERIFIED STUDENT EVIDENCE, temporal trends, causes, diagnoses, '
        'intervention effects, institutional resources, policies, offices, contact details, and procedures '
        'are unknown. If RAG matched is false, state exactly: '
        '"No verified institutional resource is currently configured."\n\n'
        'RULES\n'
        '1. State only facts contained in the verified evidence above.\n'
        '2. Do not infer causes or causal relationships.\n'
        '3. Do not change or reinterpret categorical values.\n'
        '4. Do not invent trends or temporal descriptions.\n'
        '5. Do not use causal language or promise an outcome.\n'
        '6. Separate observations from recommendations.\n'
        '7. If evidence is insufficient, say "Not enough verified evidence."\n'
        '8. Do not diagnose, invent or name an unlisted institutional resource/policy, or imply an action '
        'has already been approved or sent.\n'
        'Do not diagnose. Do not invent institutional policy. Do not make unsupported claims. Do not take '
        'or imply automatic action. Faculty review is required.\n'
        f'9. Include this exact first line: {_REVIEW_HEADER}\n'
        'Use exactly these sections after the required first line:\nOBSERVATIONS:\nRECOMMENDATIONS:'
    )


def validate_intervention_draft(body: str, context: Any) -> list[str]:
    errors: list[str] = []
    text = body.strip()
    if not text.startswith(_REVIEW_HEADER):
        errors.append('Missing required faculty-review draft framing.')
    content = re.sub(r'[*_`]', '', text.removeprefix(_REVIEW_HEADER).casefold())
    if 'observations:' not in content or 'recommendations:' not in content:
        errors.append('Draft must separate observations from recommendations.')
    sentences = re.split(r'(?<=[.!?])\s+|\n+', content)

    momentum = {str(key).casefold(): str(value).upper() for key, value in context.momentum.items()}
    metric_momentum = {
        'attendance': (r'attendance', momentum.get('attendance', 'NOT SUPPORTED')),
        'assessment': (r'assessment|exam(?:ination)?|marks?|scores?|grades?', momentum.get('assessment', 'NOT SUPPORTED')),
        'assignment': (r'assignments?|submissions?|homework|assignment engagement', momentum.get('assignment_submission', momentum.get('assignments', 'NOT SUPPORTED'))),
        'activity': (r'activities|activity', momentum.get('activity', 'NOT SUPPORTED')),
    }
    for name, (metric_pattern, classification) in metric_momentum.items():
        for descriptor_class, descriptor_pattern in _MOMENTUM_DESCRIPTORS.items():
            claim = re.search(
                rf'\b(?:{metric_pattern})\b.{{0,35}}\b(?:momentum|trend|is|are|was|were|has been|have been|remains|shows?|demonstrates?)\b.{{0,25}}\b(?:{descriptor_pattern})\b|\b(?:{descriptor_pattern})\b.{{0,35}}\b(?:in|of|for)\b.{{0,25}}\b(?:{metric_pattern})\b',
                content,
                re.IGNORECASE,
            )
            if claim and classification != descriptor_class:
                errors.append(f'Unsupported {name} momentum claim ({descriptor_class}; verified: {classification}).')

    risk_trend = re.search(rf'\brisk\b.{{0,35}}\b(?:{_TREND}|stable|unchanged)\b|\b(?:{_TREND})\b.{{0,25}}\brisk\b', content, re.IGNORECASE)
    if risk_trend and risk_trend.group(0).casefold() not in ' '.join(context.temporal_evidence).casefold():
        errors.append('Unsupported risk trend claim.')

    unsupported_temporal = []
    for sentence in sentences:
        for match in re.finditer(rf'\b(?:{_TEMPORAL})\b', sentence, re.IGNORECASE):
            if re.search(r'\b(?:risk|attendance|assessment|assignments?|submissions?|activity|engagement|momentum|trend|progress|fluctuat\w*|volatil\w*|declin\w*|improv\w*)\b', sentence):
                if match.group(0).casefold() not in ' '.join(context.temporal_evidence).casefold():
                    unsupported_temporal.append(match.group(0))
    if unsupported_temporal:
        errors.append(f'Unsupported temporal claim: {unsupported_temporal[0]}')

    numeric_checks = (
        (r'\battendance\b\s*(?:is|at|=|:)\s*(\d+(?:\.\d+)?)\s*(%)?', float(context.attendance), 'attendance'),
        (r'\b(?:assessment(?: performance| score)?|exam score|mark|score)\b\s*(?:is|at|=|:)\s*(\d+(?:\.\d+)?)\s*(%)?', float(context.assessment), 'assessment'),
        (r'\b(?:assignment engagement|engagement value)\b\s*(?:is|at|=|:)\s*(\d+(?:\.\d+)?)\s*(%)?', float(context.assignment_engagement), 'assignment engagement'),
    )
    for pattern, expected, label in numeric_checks:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            if not math.isclose(float(match.group(1)), expected, rel_tol=1e-4, abs_tol=0.01):
                errors.append(f'Draft states an {label} value that conflicts with verified evidence.')
    for match in re.finditer(r'\b(?:risk probability|probability)\b\s*(?:is|of|=|:)\s*(0?\.\d+|1(?:\.0+)?|\d+(?:\.\d+)?)\s*(%)?', content, re.IGNORECASE):
        stated_probability = float(match.group(1)) / (100 if match.group(2) else 1)
        if not math.isclose(stated_probability, float(context.risk_probability), rel_tol=1e-4, abs_tol=0.0001):
            errors.append('Draft states a risk probability that conflicts with verified evidence.')

    for sentence in sentences:
        feature_terms = r'attendance|assessment|exam(?:ination)?|marks?|scores?|grades?|assignments?|submissions?|homework|engagement'
        outcome_terms = r'risk|probability|performance|grade|score|outcome|result'
        causal_claim = re.search(
            rf'\b(?:{feature_terms})\b.{{0,55}}\b(?:{_CAUSAL})\b.{{0,55}}\b(?:{outcome_terms})\b',
            sentence,
            re.IGNORECASE,
        ) or re.search(
            rf'\b(?:{outcome_terms})\b.{{0,55}}\b(?:because|due to|as a result of|caused by|driven by)\b.{{0,45}}\b(?:{feature_terms})\b',
            sentence,
            re.IGNORECASE,
        )
        if causal_claim:
            claim_text = causal_claim.group(0).casefold()
            if claim_text not in ' '.join(context.causal_evidence).casefold():
                errors.append(f'Unsupported causal relationship: {sentence.strip()}')
        if re.search(r'\b(?:attendance|assessment|assignments?|submissions?|activity|engagement)\b.{0,55}\b(?:contributors?|contribute|impact|influence|affect)\b.{0,40}\b(?:risk|probability|outcome)\b', sentence, re.IGNORECASE):
            errors.append(f'Unsupported factor-to-risk attribution: {sentence.strip()}')
        if re.search(r'\bshap\b', sentence, re.IGNORECASE) and re.search(r'\b(?:impact|influence|driver|cause|contributor)\w*\b', sentence, re.IGNORECASE):
            errors.append(f'SHAP contributions must not be presented as causes or drivers: {sentence.strip()}')
        if re.search(r'\b(?:positive|negative)\s+sign\b', sentence, re.IGNORECASE):
            errors.append(f'Unsupported evaluative interpretation: {sentence.strip()}')
        if re.search(r'\b(?:assessment|attendance|assignment|academic|performance)\s+gaps?\b|\b(?:poor|weak|low)\s+(?:academic\s+)?performance\b', sentence, re.IGNORECASE):
            errors.append(f'Unsupported evaluative academic claim: {sentence.strip()}')
        if re.search(r'\b(?:will|would|can|could|may|might|should)\s+(?:likely\s+)?(?:reduce|improve|lower|raise|decrease|increase|prevent)\b.{0,45}\b(?:risk|probability|performance|outcome)\b', sentence, re.IGNORECASE):
            errors.append(f'Unsupported intervention effect or outcome promise: {sentence.strip()}')
        if re.search(r'\b(?:student|they|he|she)\s+(?:has|have|is experiencing|suffers from|appears to have)\s+(?:depression|anxiety|adhd|autism|a mental|a psychological)\b', sentence, re.IGNORECASE):
            errors.append('Draft contains an unsupported diagnosis.')
        if re.search(r'\b(?:student|they|he|she)\s+(?:is|are|seems|appears to be)\s+(?:struggling|having difficulty|unable to cope|overwhelmed)\b', sentence, re.IGNORECASE):
            errors.append('Draft makes an unsupported claim about the student’s personal state.')

    if re.search(r'\b(?:high|low|strong|weak)\s+probability\b', content, re.IGNORECASE):
        errors.append('Draft characterizes risk probability without an explicitly verified descriptor.')

    for match in re.finditer(r'\b(?:high|medium|low|moderate|elevated|severe)\s+risk\b|\brisk(?: level)?\s+(?:is|currently is)\s+(?:high|medium|low|moderate|elevated|severe)\b', content, re.IGNORECASE):
        stated_level = re.search(r'\b(high|medium|low|moderate|elevated|severe)\b', match.group(0), re.IGNORECASE)
        if stated_level and stated_level.group(1).casefold() != str(context.risk_level).casefold():
            errors.append('Draft states a risk level that conflicts with the verified current risk level.')

    resources = context.institutional_resources
    verified_text = ' '.join(f"{item.get('title', '')} {item.get('text', '')}" for item in resources).casefold()
    if not resources and 'no verified institutional resource is currently configured.' not in content:
        errors.append('Draft omits the required notice that no verified institutional resource is configured.')
    if re.search(r'\b(?:https?://|www\.)\S+|\b\+?\d[\d\s().-]{7,}\d\b', content, re.IGNORECASE):
        if not resources or not any(value in verified_text for value in re.findall(r'(?:https?://|www\.)\S+|\+?\d[\d\s().-]{7,}\d', content, re.IGNORECASE)):
            errors.append('Draft includes an unverified URL or phone number.')
    for policy_claim in re.finditer(r'\b(?:institutional|university|campus)?\s*policy\s+(?:requires|allows|states|mandates|provides|ensures|offers|is in effect)\b', content, re.IGNORECASE):
        if policy_claim.group(0).casefold() not in verified_text:
            errors.append('Draft makes an unsupported institutional policy claim.')
    for match in re.finditer(
        r'\b(?:[a-z][a-z&\' -]{1,50}\b(?:office|center|centre|department|service|services|program|clinic|hotline)|(?:contact|call|email|visit|use|access|schedule with|go to|reach out to)\s+(?:the\s+)?[a-z][a-z&\' -]{1,50}\b(?:office|center|centre|department|service|services|program|clinic|hotline))\b',
        content,
        re.IGNORECASE,
    ):
        named_resource = match.group(0).strip()
        if named_resource.casefold() not in verified_text:
            errors.append(f'Draft names an unverified institutional resource: {named_resource}.')

    return list(dict.fromkeys(errors))