from dataclasses import dataclass
import re

from .exceptions import InvalidAIResponse


DIAGNOSTIC_RESPONSE_FIELDS = {
    'possible_misconception',
    'diagnostic_confidence',
    'response_type',
    'message',
    'hint_level',
    'should_reveal_solution',
}
RESPONSE_TYPE_HINT_LEVELS = {
    'guiding_question': 1,
    'concept_reminder': 2,
    'related_example': 3,
    'partial_method': 4,
}
TEACH_BACK_RESPONSE_FIELDS = {
    'field_evaluations',
    'misconception_code',
    'follow_up_question',
}
TEACH_BACK_FIELD_EVALUATION_FIELDS = {'field', 'understood', 'feedback'}
DIAGNOSIS_EVALUATION_FIELDS = DIAGNOSTIC_RESPONSE_FIELDS | {'understood', 'feedback'}
HINT_RESPONSE_FIELDS = {
    'possible_misconception',
    'response_type',
    'message',
    'hint_level',
    'should_reveal_solution',
}


@dataclass(frozen=True)
class DiagnosticResponse:
    possible_misconception: str
    diagnostic_confidence: float
    response_type: str
    message: str
    hint_level: int
    should_reveal_solution: bool = False

    def to_dict(self):
        return {
            'possible_misconception': self.possible_misconception,
            'diagnostic_confidence': self.diagnostic_confidence,
            'response_type': self.response_type,
            'message': self.message,
            'hint_level': self.hint_level,
            'should_reveal_solution': self.should_reveal_solution,
        }

    @classmethod
    def schema_contract(cls, *, allowed_misconception_codes=None,
                        allowed_response_types=None, max_hint_level=4):
        misconception_schema = {'type': 'string'}
        if allowed_misconception_codes is not None:
            misconception_schema['enum'] = list(allowed_misconception_codes)
        response_types = list(allowed_response_types or RESPONSE_TYPE_HINT_LEVELS)
        return {
            'type': 'object',
            'required': sorted(DIAGNOSTIC_RESPONSE_FIELDS),
            'additionalProperties': False,
            'properties': {
                'possible_misconception': misconception_schema,
                'diagnostic_confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
                'response_type': {'type': 'string', 'enum': response_types},
                'message': {
                    'type': 'string',
                    'description': (
                        'Exactly one concise diagnostic question. Do not include example code, '
                        'syntax, suggested edits, answers, or additional questions.'
                    ),
                },
                'hint_level': {'type': 'integer', 'minimum': 1, 'maximum': max_hint_level},
                'should_reveal_solution': {'type': 'boolean', 'enum': [False]},
            },
        }


def validate_diagnostic_response(payload, *, allowed_response_types=('guiding_question',),
                                 max_hint_level=1, allow_solution=False,
                                 allowed_misconception_codes=None):
    if isinstance(payload, DiagnosticResponse):
        payload = payload.to_dict()
    if not isinstance(payload, dict):
        raise InvalidAIResponse('The AI response must be a JSON object.')
    if set(payload) != DIAGNOSTIC_RESPONSE_FIELDS:
        raise InvalidAIResponse('The AI response contains missing or unauthorized fields.')

    misconception = payload['possible_misconception']
    confidence = payload['diagnostic_confidence']
    response_type = payload['response_type']
    message = payload['message']
    hint_level = payload['hint_level']
    should_reveal = payload['should_reveal_solution']

    if (
        not isinstance(misconception, str)
        or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}', misconception)
    ):
        raise InvalidAIResponse('The possible misconception must be a stable code.')
    if allowed_misconception_codes is not None and misconception not in allowed_misconception_codes:
        raise InvalidAIResponse('The possible misconception is not curated for this exercise.')
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise InvalidAIResponse('Diagnostic confidence must be between 0 and 1.')
    if response_type not in RESPONSE_TYPE_HINT_LEVELS or response_type not in allowed_response_types:
        raise InvalidAIResponse('The response type is not allowed at this workflow step.')
    if isinstance(hint_level, bool) or not isinstance(hint_level, int):
        raise InvalidAIResponse('Hint level must be an integer.')
    if hint_level != RESPONSE_TYPE_HINT_LEVELS[response_type] or hint_level > max_hint_level:
        raise InvalidAIResponse('The response exceeds the allowed hint level.')
    if not isinstance(should_reveal, bool) or (should_reveal and not allow_solution):
        raise InvalidAIResponse('The response is not allowed to reveal a solution.')
    if not isinstance(message, str) or not message.strip() or len(message.strip()) > 1000:
        raise InvalidAIResponse('The response message must be concise and non-empty.')
    normalized_message = message.strip().casefold()
    if '```' in message or normalized_message.startswith(('replace ', 'the complete solution is', 'use this code')):
        raise InvalidAIResponse('The response appears to reveal a direct solution.')
    if message.count('?') != 1 or not message.strip().endswith('?'):
        raise InvalidAIResponse('The response must contain exactly one diagnostic question.')
    if any(marker in normalized_message for marker in ('e.g.', 'for example', 'such as')):
        raise InvalidAIResponse('A guiding question cannot include a related example.')

    return DiagnosticResponse(
        possible_misconception=misconception,
        diagnostic_confidence=float(confidence),
        response_type=response_type,
        message=message.strip(),
        hint_level=hint_level,
        should_reveal_solution=should_reveal,
    )


@dataclass(frozen=True)
class TeachBackFieldEvaluation:
    field: str
    understood: bool
    feedback: str

    def to_dict(self):
        return {
            'field': self.field,
            'understood': self.understood,
            'feedback': self.feedback,
        }


@dataclass(frozen=True)
class TeachBackResponse:
    field_evaluations: tuple
    misconception_code: str
    follow_up_question: str

    def to_dict(self):
        return {
            'field_evaluations': [item.to_dict() for item in self.field_evaluations],
            'misconception_code': self.misconception_code,
            'follow_up_question': self.follow_up_question,
        }

    @classmethod
    def schema_contract(cls, *, expected_fields, allowed_misconception_codes):
        fields = list(expected_fields)
        misconception_codes = ['none', *allowed_misconception_codes]
        return {
            'type': 'object',
            'required': sorted(TEACH_BACK_RESPONSE_FIELDS),
            'additionalProperties': False,
            'properties': {
                'field_evaluations': {
                    'type': 'array',
                    'minItems': len(fields),
                    'maxItems': len(fields),
                    'items': {
                        'type': 'object',
                        'required': sorted(TEACH_BACK_FIELD_EVALUATION_FIELDS),
                        'additionalProperties': False,
                        'properties': {
                            'field': {'type': 'string', 'enum': fields},
                            'understood': {'type': 'boolean'},
                            'feedback': {
                                'type': 'string',
                                'description': (
                                    'A concise reason tied to this answer. Empty when the answer '
                                    'shows understanding.'
                                ),
                            },
                        },
                    },
                },
                'misconception_code': {'type': 'string', 'enum': misconception_codes},
                'follow_up_question': {
                    'type': 'string',
                    'description': (
                        'Exactly one focused question when a core idea needs revision; otherwise empty.'
                    ),
                },
            },
        }


def validate_teach_back_response(payload, *, expected_fields, allowed_misconception_codes):
    if isinstance(payload, TeachBackResponse):
        payload = payload.to_dict()
    if not isinstance(payload, dict) or set(payload) != TEACH_BACK_RESPONSE_FIELDS:
        raise InvalidAIResponse('The Teach-Back response contains missing or unauthorized fields.')

    raw_evaluations = payload['field_evaluations']
    expected = tuple(expected_fields)
    if not isinstance(raw_evaluations, list) or len(raw_evaluations) != len(expected):
        raise InvalidAIResponse('The Teach-Back response must evaluate every rubric field once.')

    evaluations = []
    seen_fields = set()
    for item in raw_evaluations:
        if not isinstance(item, dict) or set(item) != TEACH_BACK_FIELD_EVALUATION_FIELDS:
            raise InvalidAIResponse('A Teach-Back field evaluation has an invalid shape.')
        field = item['field']
        understood = item['understood']
        feedback = item['feedback']
        if field not in expected or field in seen_fields:
            raise InvalidAIResponse('Teach-Back fields must be curated and unique.')
        if not isinstance(understood, bool):
            raise InvalidAIResponse('Teach-Back understanding must be boolean.')
        if not isinstance(feedback, str) or len(feedback.strip()) > 500:
            raise InvalidAIResponse('Teach-Back feedback must be concise text.')
        if not understood and not feedback.strip():
            raise InvalidAIResponse('An answer needing revision must include specific feedback.')
        seen_fields.add(field)
        evaluations.append(TeachBackFieldEvaluation(
            field=field,
            understood=understood,
            feedback=feedback.strip(),
        ))
    if seen_fields != set(expected):
        raise InvalidAIResponse('The Teach-Back response omitted a rubric field.')

    misconception_code = payload['misconception_code']
    if misconception_code not in {'none', *allowed_misconception_codes}:
        raise InvalidAIResponse('The Teach-Back misconception is not curated for this exercise.')
    follow_up = payload['follow_up_question']
    if not isinstance(follow_up, str) or len(follow_up.strip()) > 500:
        raise InvalidAIResponse('The Teach-Back follow-up must be concise text.')
    follow_up = follow_up.strip()
    if follow_up and (follow_up.count('?') != 1 or not follow_up.endswith('?')):
        raise InvalidAIResponse('Teach-Back may contain only one focused follow-up question.')
    needs_revision = any(not item.understood for item in evaluations)
    if misconception_code != 'none' and not needs_revision:
        raise InvalidAIResponse('A reported misconception must identify an answer needing revision.')
    if needs_revision and not follow_up:
        raise InvalidAIResponse('Teach-Back revision requires one focused follow-up question.')

    return TeachBackResponse(
        field_evaluations=tuple(evaluations),
        misconception_code=misconception_code,
        follow_up_question=follow_up,
    )


@dataclass(frozen=True)
class DiagnosisEvaluationResponse:
    understood: bool
    feedback: str
    possible_misconception: str
    diagnostic_confidence: float
    response_type: str
    message: str
    hint_level: int
    should_reveal_solution: bool

    def to_dict(self):
        return {
            'understood': self.understood,
            'feedback': self.feedback,
            'possible_misconception': self.possible_misconception,
            'diagnostic_confidence': self.diagnostic_confidence,
            'response_type': self.response_type,
            'message': self.message,
            'hint_level': self.hint_level,
            'should_reveal_solution': self.should_reveal_solution,
        }

    @classmethod
    def schema_contract(cls, *, allowed_misconception_codes, response_type,
                        hint_level, should_reveal_solution):
        return {
            'type': 'object',
            'required': sorted(DIAGNOSIS_EVALUATION_FIELDS),
            'additionalProperties': False,
            'properties': {
                'understood': {'type': 'boolean'},
                'feedback': {
                    'type': 'string',
                    'description': 'A concise semantic evaluation of the learner answer.',
                },
                'possible_misconception': {
                    'type': 'string',
                    'enum': list(allowed_misconception_codes),
                },
                'diagnostic_confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
                'response_type': {'type': 'string', 'enum': [response_type]},
                'message': {
                    'type': 'string',
                    'description': (
                        'The next easier question, or the correct conceptual answer at the final level.'
                    ),
                },
                'hint_level': {'type': 'integer', 'enum': [hint_level]},
                'should_reveal_solution': {
                    'type': 'boolean',
                    'enum': [should_reveal_solution],
                },
            },
        }


def validate_diagnosis_evaluation(payload, *, allowed_misconception_codes,
                                  response_type, hint_level, should_reveal_solution):
    if isinstance(payload, DiagnosisEvaluationResponse):
        payload = payload.to_dict()
    if not isinstance(payload, dict) or set(payload) != DIAGNOSIS_EVALUATION_FIELDS:
        raise InvalidAIResponse('The diagnosis evaluation contains missing or unauthorized fields.')

    understood = payload['understood']
    feedback = payload['feedback']
    misconception = payload['possible_misconception']
    confidence = payload['diagnostic_confidence']
    message = payload['message']
    if not isinstance(understood, bool):
        raise InvalidAIResponse('Diagnosis understanding must be boolean.')
    if not isinstance(feedback, str) or not feedback.strip() or len(feedback.strip()) > 500:
        raise InvalidAIResponse('Diagnosis feedback must be concise and non-empty.')
    if misconception not in allowed_misconception_codes:
        raise InvalidAIResponse('The diagnosis misconception is not curated for this exercise.')
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise InvalidAIResponse('Diagnostic confidence must be between 0 and 1.')
    if payload['response_type'] != response_type:
        raise InvalidAIResponse('The diagnosis response type does not match the server-selected level.')
    if payload['hint_level'] != hint_level:
        raise InvalidAIResponse('The diagnosis hint level does not match the server-selected level.')
    if payload['should_reveal_solution'] is not should_reveal_solution:
        raise InvalidAIResponse('The diagnosis response cannot control solution reveal.')
    if not isinstance(message, str) or not message.strip() or len(message.strip()) > 1500:
        raise InvalidAIResponse('The diagnosis message must be concise and non-empty.')
    message = message.strip()
    if '```' in message:
        raise InvalidAIResponse('Diagnosis feedback cannot include solution code.')
    if not should_reveal_solution and (message.count('?') != 1 or not message.endswith('?')):
        raise InvalidAIResponse('A progressive diagnosis hint must ask exactly one question.')

    return DiagnosisEvaluationResponse(
        understood=understood,
        feedback=feedback.strip(),
        possible_misconception=misconception,
        diagnostic_confidence=float(confidence),
        response_type=response_type,
        message=message,
        hint_level=hint_level,
        should_reveal_solution=should_reveal_solution,
    )


@dataclass(frozen=True)
class HintResponse:
    possible_misconception: str
    response_type: str
    message: str
    hint_level: int
    should_reveal_solution: bool

    def to_dict(self):
        return {
            'possible_misconception': self.possible_misconception,
            'response_type': self.response_type,
            'message': self.message,
            'hint_level': self.hint_level,
            'should_reveal_solution': self.should_reveal_solution,
        }

    @classmethod
    def schema_contract(cls, *, allowed_misconception_codes, response_type,
                        hint_level, should_reveal_solution):
        return {
            'type': 'object',
            'required': sorted(HINT_RESPONSE_FIELDS),
            'additionalProperties': False,
            'properties': {
                'possible_misconception': {
                    'type': 'string',
                    'enum': list(allowed_misconception_codes),
                },
                'response_type': {'type': 'string', 'enum': [response_type]},
                'message': {'type': 'string'},
                'hint_level': {'type': 'integer', 'enum': [hint_level]},
                'should_reveal_solution': {
                    'type': 'boolean',
                    'enum': [should_reveal_solution],
                },
            },
        }


def validate_hint_response(payload, *, allowed_misconception_codes, response_type,
                           hint_level, should_reveal_solution):
    if isinstance(payload, HintResponse):
        payload = payload.to_dict()
    if not isinstance(payload, dict) or set(payload) != HINT_RESPONSE_FIELDS:
        raise InvalidAIResponse('The hint response contains missing or unauthorized fields.')
    if payload['possible_misconception'] not in allowed_misconception_codes:
        raise InvalidAIResponse('The hint misconception is not curated for this exercise.')
    if payload['response_type'] != response_type:
        raise InvalidAIResponse('The hint response type does not match the server-selected level.')
    if payload['hint_level'] != hint_level:
        raise InvalidAIResponse('The hint level does not match the server-selected level.')
    if payload['should_reveal_solution'] is not should_reveal_solution:
        raise InvalidAIResponse('The hint cannot control solution reveal.')
    message = payload['message']
    if not isinstance(message, str) or not message.strip() or len(message.strip()) > 2500:
        raise InvalidAIResponse('The hint message must be concise and non-empty.')
    message = message.strip()
    normalized = message.casefold()
    if not should_reveal_solution:
        if message.count('?') != 1 or not message.endswith('?'):
            raise InvalidAIResponse('A progressive hint must ask exactly one question.')
        if '```' in message or 'def double_numbers' in normalized:
            raise InvalidAIResponse('A progressive hint cannot reveal the complete solution.')

    return HintResponse(
        possible_misconception=payload['possible_misconception'],
        response_type=response_type,
        message=message,
        hint_level=hint_level,
        should_reveal_solution=should_reveal_solution,
    )
