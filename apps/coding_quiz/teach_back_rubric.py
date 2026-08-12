from dataclasses import dataclass


LOOP_VALUES_TEACH_BACK_RUBRIC = {
    'criteria': [
        {
            'id': 'identify_original_issue',
            'field': 'original_issue',
            'required_for_clear': False,
            'meaning': 'Identifies what the first attempt did incorrectly or left uncertain.',
            'required_groups': [[
                'loop variable', 'current value', 'which value', 'current item',
                'unchanged', 'without transforming', 'whole list',
                'biến vòng lặp', 'giá trị hiện tại', 'phần tử hiện tại',
                'không biến đổi', 'cả danh sách',
            ]],
            'feedback': 'The original issue is not identified using evidence from the first attempt.',
            'follow_up_question': 'What value did your original loop use or transform incorrectly?',
        },
        {
            'id': 'explain_failure_reason',
            'field': 'failure_reason',
            'required_for_clear': True,
            'meaning': 'Connects one loop iteration and its current value to the wrong result.',
            'required_groups': [
                ['each', 'every', 'current', 'item', 'value', 'element', 'mỗi', 'từng', 'phần tử', 'giá trị'],
                ['unchanged', 'not transform', 'did not transform', 'returned', 'whole list', 'failed',
                 'không đổi', 'không biến đổi', 'trả về', 'cả danh sách', 'thất bại'],
            ],
            'feedback': 'The explanation does not yet connect one loop iteration to the wrong result.',
            'follow_up_question': 'During one iteration, what value did the loop variable hold, and why did the old operation produce the wrong result?',
        },
        {
            'id': 'explain_correction',
            'field': 'correction',
            'required_for_clear': True,
            'meaning': 'Explains that each current value is transformed before being collected.',
            'required_groups': [
                ['each', 'current', 'item', 'value', 'element', 'mỗi', 'phần tử', 'giá trị'],
                ['double', 'multiply', '* 2', 'transform', 'append', 'collect', 'nhân', 'gấp đôi', 'biến đổi', 'thêm'],
            ],
            'feedback': 'The correction does not specify what happens to each current value.',
            'follow_up_question': 'What operation should be applied to the current item before it is added to the result?',
        },
        {
            'id': 'name_underlying_concept',
            'field': 'concept',
            'required_for_clear': True,
            'meaning': 'Understands that a loop variable represents one item during an iteration.',
            'required_groups': [
                ['loop', 'for', 'iteration', 'vòng lặp', 'lặp'],
                ['item', 'value', 'element', 'one at a time', 'phần tử', 'giá trị', 'từng'],
            ],
            'feedback': 'The underlying loop-variable concept is not explained yet.',
            'follow_up_question': 'In a for loop, what does the loop variable represent during one iteration?',
        },
        {
            'id': 'explain_prevention',
            'field': 'prevention',
            'required_for_clear': False,
            'meaning': 'Provides a concrete future check, such as tracing a small input.',
            'required_groups': [
                ['trace', 'check', 'test', 'small input', 'step', 'theo dõi', 'kiểm tra', 'dữ liệu nhỏ', 'từng bước'],
                ['loop', 'iteration', 'item', 'value', 'input', 'vòng lặp', 'lần lặp', 'phần tử', 'giá trị', 'đầu vào'],
            ],
            'feedback': 'The prevention plan does not give a concrete way to check this concept next time.',
            'follow_up_question': 'What small trace or check will you perform to verify the loop variable next time?',
        },
    ],
    'misconceptions': [
        {
            'code': 'loop-value-misuse',
            'fields': ['correction', 'concept'],
            'indicators': [
                'loop variable holds the whole list',
                'loop variable is the entire list',
                'double the whole list after the loop',
                'double the entire list after the loop',
                'biến vòng lặp chứa cả danh sách',
                'nhân cả danh sách sau vòng lặp',
            ],
            'feedback': 'The response still treats the loop variable as the whole collection.',
            'follow_up_question': 'During exactly one loop iteration, does the loop variable hold one item or the entire list?',
        },
    ],
}


@dataclass(frozen=True)
class TeachBackEvaluation:
    result: str
    feedback: str
    follow_up_question: str
    rubric_evidence: dict
    misconception_code: str = ''


def _is_nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def _valid_rubric(rubric):
    if not isinstance(rubric, dict):
        return False
    criteria = rubric.get('criteria')
    misconceptions = rubric.get('misconceptions', [])
    if not isinstance(criteria, list) or not criteria or not isinstance(misconceptions, list):
        return False
    for criterion in criteria:
        if not isinstance(criterion, dict) or not all(
            _is_nonempty_string(criterion.get(key))
            for key in ('id', 'field', 'feedback', 'follow_up_question')
        ):
            return False
        groups = criterion.get('required_groups')
        if not isinstance(groups, list) or not groups:
            return False
        if any(
            not isinstance(group, list)
            or not group
            or not all(_is_nonempty_string(marker) for marker in group)
            for group in groups
        ):
            return False
    for misconception in misconceptions:
        if not isinstance(misconception, dict) or not all(
            _is_nonempty_string(misconception.get(key))
            for key in ('code', 'feedback', 'follow_up_question')
        ):
            return False
        fields = misconception.get('fields')
        indicators = misconception.get('indicators')
        if (
            not isinstance(fields, list)
            or not fields
            or not all(_is_nonempty_string(field) for field in fields)
            or not isinstance(indicators, list)
            or not indicators
            or not all(_is_nonempty_string(indicator) for indicator in indicators)
        ):
            return False
    return True


def evaluate_teach_back(response, rubric):
    if not _valid_rubric(rubric):
        return TeachBackEvaluation(
            result='PARTIAL_UNDERSTANDING',
            feedback='The exercise Teach-Back rubric is unavailable, so understanding was not assumed.',
            follow_up_question='Can you explain which value the loop variable represents during one iteration?',
            rubric_evidence={'rubric_valid': False},
        )

    normalized = {
        field: str(answer).casefold()
        for field, answer in response.items()
    }
    misconception_match = None
    for misconception in rubric.get('misconceptions', []):
        fields = misconception.get('fields', [])
        indicators = misconception.get('indicators', [])
        matched = next((
            indicator
            for field in fields
            for indicator in indicators
            if indicator.casefold() in normalized.get(field, '')
        ), None)
        if matched:
            misconception_match = (misconception, matched)
            break

    passed_criteria = []
    field_evaluations = []
    first_unmet = None
    for criterion in rubric['criteria']:
        answer = normalized.get(criterion.get('field'), '')
        required_groups = criterion.get('required_groups', [])
        criterion_passed = bool(required_groups) and all(
            any(marker.casefold() in answer for marker in group)
            for group in required_groups
        )
        if criterion_passed:
            passed_criteria.append(criterion['id'])
        elif first_unmet is None:
            first_unmet = criterion
        field_evaluations.append({
            'field': criterion['field'],
            'understood': criterion_passed,
            'feedback': '' if criterion_passed else criterion['feedback'],
        })

    if misconception_match:
        misconception, matched = misconception_match
        misconception_fields = set(misconception.get('fields', []))
        for field_evaluation in field_evaluations:
            if field_evaluation['field'] in misconception_fields:
                field_evaluation['understood'] = False
                field_evaluation['feedback'] = misconception['feedback']
        return TeachBackEvaluation(
            result='MISCONCEPTION_REMAINS',
            feedback=misconception['feedback'],
            follow_up_question=misconception['follow_up_question'],
            rubric_evidence={
                'rubric_valid': True,
                'misconception_code': misconception['code'],
                'matched_indicator': matched,
                'field_evaluations': field_evaluations,
            },
            misconception_code=misconception['code'],
        )

    if first_unmet:
        return TeachBackEvaluation(
            result='PARTIAL_UNDERSTANDING',
            feedback=first_unmet['feedback'],
            follow_up_question=first_unmet['follow_up_question'],
            rubric_evidence={
                'rubric_valid': True,
                'passed_criteria': passed_criteria,
                'unmet_criterion': first_unmet['id'],
                'field_evaluations': field_evaluations,
            },
        )

    return TeachBackEvaluation(
        result='CLEAR_UNDERSTANDING',
        feedback='Every Teach-Back rubric criterion was satisfied.',
        follow_up_question='',
        rubric_evidence={
            'rubric_valid': True,
            'passed_criteria': passed_criteria,
            'field_evaluations': field_evaluations,
        },
    )
