from dataclasses import dataclass

from .client import generate_ai_response
from .exceptions import AIEngineError, InvalidAIResponse
from .schemas import (
    DiagnosticResponse,
    DiagnosisEvaluationResponse,
    HintResponse,
    TeachBackResponse,
    validate_diagnosis_evaluation,
    validate_hint_response,
    validate_diagnostic_response,
    validate_teach_back_response,
)


@dataclass(frozen=True)
class OrchestratedDiagnostic:
    response: DiagnosticResponse
    source: str
    failure_code: str = ''


@dataclass(frozen=True)
class OrchestratedTeachBack:
    response: TeachBackResponse
    source: str
    failure_code: str = ''


@dataclass(frozen=True)
class OrchestratedDiagnosisEvaluation:
    response: DiagnosisEvaluationResponse
    source: str
    failure_code: str = ''


@dataclass(frozen=True)
class OrchestratedHint:
    response: HintResponse
    source: str
    failure_code: str = ''


def orchestrate_diagnostic(*, system_prompt, user_prompt, curated_fallback,
                           allowed_misconception_codes, provider=None):
    try:
        raw_response = generate_ai_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=DiagnosticResponse.schema_contract(
                allowed_misconception_codes=allowed_misconception_codes,
                allowed_response_types=('guiding_question',),
                max_hint_level=1,
            ),
            provider=provider,
        )
        response = validate_diagnostic_response(
            raw_response,
            allowed_misconception_codes=allowed_misconception_codes,
        )
        return OrchestratedDiagnostic(response=response, source='AI')
    except AIEngineError as exc:
        failure_code = type(exc).__name__

    try:
        safe_fallback = validate_diagnostic_response(
            curated_fallback,
            allowed_misconception_codes=allowed_misconception_codes,
        )
    except InvalidAIResponse:
        safe_fallback = DiagnosticResponse(
            possible_misconception='needs-diagnosis',
            diagnostic_confidence=0.0,
            response_type='guiding_question',
            message='Which value changes during one iteration, and what should happen to it?',
            hint_level=1,
            should_reveal_solution=False,
        )
        failure_code = f'{failure_code}+InvalidCuratedFallback'
    return OrchestratedDiagnostic(
        response=safe_fallback,
        source='CURATED_FALLBACK',
        failure_code=failure_code,
    )


def orchestrate_teach_back(*, system_prompt, user_prompt, curated_fallback,
                           expected_fields, allowed_misconception_codes, provider=None):
    try:
        raw_response = generate_ai_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=TeachBackResponse.schema_contract(
                expected_fields=expected_fields,
                allowed_misconception_codes=allowed_misconception_codes,
            ),
            provider=provider,
        )
        response = validate_teach_back_response(
            raw_response,
            expected_fields=expected_fields,
            allowed_misconception_codes=allowed_misconception_codes,
        )
        return OrchestratedTeachBack(response=response, source='AI')
    except AIEngineError as exc:
        failure_code = type(exc).__name__

    safe_fallback = validate_teach_back_response(
        curated_fallback,
        expected_fields=expected_fields,
        allowed_misconception_codes=allowed_misconception_codes,
    )
    return OrchestratedTeachBack(
        response=safe_fallback,
        source='CURATED_FALLBACK',
        failure_code=failure_code,
    )


def orchestrate_diagnosis_evaluation(*, system_prompt, user_prompt, curated_fallback,
                                     allowed_misconception_codes, response_type,
                                     hint_level, should_reveal_solution, provider=None):
    validation_options = {
        'allowed_misconception_codes': allowed_misconception_codes,
        'response_type': response_type,
        'hint_level': hint_level,
        'should_reveal_solution': should_reveal_solution,
    }
    try:
        raw_response = generate_ai_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=DiagnosisEvaluationResponse.schema_contract(**validation_options),
            provider=provider,
        )
        response = validate_diagnosis_evaluation(raw_response, **validation_options)
        return OrchestratedDiagnosisEvaluation(response=response, source='AI')
    except AIEngineError as exc:
        failure_code = type(exc).__name__

    safe_fallback = validate_diagnosis_evaluation(curated_fallback, **validation_options)
    return OrchestratedDiagnosisEvaluation(
        response=safe_fallback,
        source='CURATED_FALLBACK',
        failure_code=failure_code,
    )


def orchestrate_hint(*, system_prompt, user_prompt, curated_fallback,
                     allowed_misconception_codes, response_type, hint_level,
                     should_reveal_solution, provider=None):
    validation_options = {
        'allowed_misconception_codes': allowed_misconception_codes,
        'response_type': response_type,
        'hint_level': hint_level,
        'should_reveal_solution': should_reveal_solution,
    }
    try:
        raw_response = generate_ai_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=HintResponse.schema_contract(**validation_options),
            provider=provider,
        )
        response = validate_hint_response(raw_response, **validation_options)
        return OrchestratedHint(response=response, source='AI')
    except AIEngineError as exc:
        failure_code = type(exc).__name__

    safe_fallback = validate_hint_response(curated_fallback, **validation_options)
    return OrchestratedHint(
        response=safe_fallback,
        source='CURATED_FALLBACK',
        failure_code=failure_code,
    )
