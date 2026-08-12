import re


LOOP_VALUE_MISCONCEPTION = 'loop-value-misuse'

ELEMENT_TERMS = (
    'each', 'every', 'current', 'item', 'value', 'element', 'number', 'word',
    'member', 'iterator',
    'mỗi', 'từng', 'hiện tại', 'phần tử', 'giá trị', 'số', 'từ',
)
DIAGNOSIS_ACTION_TERMS = (
    'double', 'multiply', 'append', 'add', 'collect', 'transform', 'use',
    'change', 'store', 'storing', 'doubled', 'doubling', 'multiplied',
    'appended', 'adding', 'collected', 'transformed', 'transforming', 'used',
    'changed', 'stored',
    'nhân', 'gấp đôi', 'thêm', 'biến đổi', 'dùng',
)
TRANSFER_ACTION_TERMS = (
    'length', 'len', 'map', 'transform', 'convert', 'append', 'collect',
    'độ dài', 'biến đổi', 'chuyển', 'thêm',
)


def diagnosis_confirms_loop_value_misconception(answer, *, action_terms=None):
    normalized = answer.casefold()
    identifies_current_element = _contains_term(normalized, ELEMENT_TERMS)
    identifies_required_action = _contains_term(
        normalized,
        tuple(action_terms or DIAGNOSIS_ACTION_TERMS),
    )
    return not (identifies_current_element and identifies_required_action)


def _contains_term(text, terms):
    return any(
        re.search(rf'(?<!\w){re.escape(term)}(?!\w)', text)
        for term in terms
    )


def transfer_repeats_loop_value_misconception(*, source_code, reasoning, action_terms=None):
    normalized_code = source_code.casefold()
    normalized_reasoning = reasoning.casefold()
    iterates_values = 'for ' in normalized_code or 'map(' in normalized_code
    explains_current_element = _contains_term(normalized_reasoning, ELEMENT_TERMS)
    explains_transformation = _contains_term(
        normalized_reasoning,
        tuple(action_terms or TRANSFER_ACTION_TERMS),
    )
    return not (iterates_values and explains_current_element and explains_transformation)
