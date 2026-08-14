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

GENERIC_CONCEPT_TERMS = {
    'conditionals': ('if', 'else', 'condition', 'branch'),
    'function_basics': ('function', 'parameter', 'return'),
    'list_1d_operations': ('list', 'element', 'number'),
    'list_2d_traversal': ('matrix', 'row', 'list'),
    'string_operations': ('string', 'character', 'text'),
    'recursion': ('recursion', 'base case', 'function'),
    'binary_search': ('binary search', 'middle', 'sorted'),
    'stack': ('stack', 'last in', 'last out'),
    'queue': ('queue', 'front', 'back'),
    'sorting': ('sort', 'smallest', 'list'),
    'hash_maps': ('dictionary', 'key', 'value'),
    'graphs': ('graph', 'node', 'visited'),
    'dynamic_programming': ('dynamic programming', 'state', 'previous'),
    'set_operations': ('set', 'unique', 'member'),
    'list_comprehensions': ('comprehension', 'list', 'expression'),
    'exception_handling': ('try', 'except', 'error'),
    'numeric_algorithms': ('number', 'remainder', 'divisor'),
    'two_pointers': ('pointer', 'left', 'right'),
    'sliding_window': ('window', 'left', 'right'),
    'greedy_algorithms': ('greedy', 'choice', 'smallest'),
    'backtracking': ('backtracking', 'choice', 'recursive'),
}


def diagnosis_confirms_loop_value_misconception(answer, *, action_terms=None):
    normalized = answer.casefold()
    identifies_current_element = _contains_term(normalized, ELEMENT_TERMS)
    identifies_required_action = _contains_term(
        normalized,
        tuple(action_terms or DIAGNOSIS_ACTION_TERMS),
    )
    return not (identifies_current_element and identifies_required_action)


def diagnosis_confirms_misconception(answer, *, misconception_code=None,
                                     concept=None, action_terms=None):
    """Return whether an answer still misses the concept-specific core idea."""
    normalized = answer.casefold()
    if misconception_code == 'dictionary-key-misuse' or concept == 'dictionary_keys':
        value_terms = tuple(action_terms or ()) + (
            'value', 'lookup', 'get', 'fallback', 'grade', 'score', 'point',
            'giá trị', 'điểm', 'tra', 'tìm', 'dùng 0', 'trả về 0',
        )
        return not (
            _contains_term(normalized, ('key', 'name', 'student', 'tên', 'học sinh'))
            and _contains_term(normalized, value_terms)
        )
    if misconception_code == 'function-parameter-misuse' or concept == 'function_parameters_and_return':
        return_terms = tuple(action_terms or ()) + (
            'zero', 'return', 'divide', 'check', 'không', 'trả về', 'chia', 'kiểm tra',
        )
        return not (
            _contains_term(normalized, (
                'parameter', 'argument', 'denominator', 'input', 'tham số', 'đối số', 'mẫu số',
            ))
            and _contains_term(normalized, return_terms)
        )
    if misconception_code == 'list-index-misuse' or concept == 'list_indexing':
        boundary_terms = tuple(action_terms or ()) + (
            'empty', 'none', 'return', 'check', 'rỗng', 'trả về', 'kiểm tra',
        )
        return not (
            _contains_term(normalized, (
                'index', 'position', 'first', 'item', 'chỉ số', 'vị trí', 'đầu tiên', 'phần tử',
            ))
            and _contains_term(normalized, boundary_terms)
        )
    if concept in GENERIC_CONCEPT_TERMS:
        return not (
            _contains_term(normalized, GENERIC_CONCEPT_TERMS[concept])
            and _contains_term(normalized, tuple(action_terms or ()))
        )
    return diagnosis_confirms_loop_value_misconception(answer, action_terms=action_terms)


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


def transfer_repeats_misconception(*, source_code, reasoning, misconception_code,
                                    action_terms=None):
    """Check whether a confirmed concept-specific error appears in Transfer."""
    code = source_code.casefold()
    text = reasoning.casefold()
    terms = tuple(action_terms or ())
    if misconception_code == 'dictionary-key-misuse':
        safe_lookup = '.get(' in code or (' in ' in code and 'if ' in code)
        explains_key = _contains_term(text, ('key', 'name', 'student'))
        explains_value = _contains_term(text, terms or ('value', 'lookup', 'fallback'))
        return not (safe_lookup and explains_key and explains_value)
    if misconception_code == 'function-parameter-misuse':
        checks_zero = 'if ' in code and ('== 0' in code or '!= 0' in code)
        explains_parameters = _contains_term(text, ('parameter', 'argument', 'denominator', 'input'))
        explains_return = _contains_term(text, terms or ('zero', 'return', 'divide'))
        return not (checks_zero and explains_parameters and explains_return)
    if misconception_code == 'list-index-misuse':
        checks_empty = 'if ' in code and ('items[0]' in code or 'items[-1]' in code or 'items [-1]' in code)
        explains_index = _contains_term(text, ('index', 'position', 'first', 'last'))
        explains_boundary = _contains_term(text, terms or ('empty', 'none', 'return'))
        return not (checks_empty and explains_index and explains_boundary)
    generic_rules = {
        'if-else-branch-misuse': 'if ' in code,
        'function-return-misuse': 'def ' in code and 'return ' in code,
        'one-dimensional-list-misuse': 'for ' in code or 'sum(' in code,
        'two-dimensional-list-misuse': code.count('for ') >= 2,
        'string-operation-misuse': any(marker in code for marker in ('.upper(', '[::-1]', 'len(', '.lower(')),
        'recursion-base-case-misuse': 'return ' in code and code.count('def ') == 1 and '(' in code,
        'binary-search-boundary-misuse': 'while ' in code and 'middle' in code,
        'stack-order-misuse': '.append(' in code and '.pop(' in code,
        'queue-order-misuse': '[1:]' in code or 'pop(0)' in code,
        'sorting-invariant-misuse': 'min(' in code or 'max(' in code or 'sorted(' in code,
        'hash-map-complement-misuse': '{}' in code or 'seen' in code,
        'graph-visited-misuse': 'visited' in code and ('stack' in code or 'queue' in code),
        'dynamic-programming-state-misuse': 'for ' in code and 'return ' in code,
        'set-operation-misuse': 'set(' in code,
        'comprehension-misuse': '[' in code and 'for ' in code,
        'exception-handling-misuse': 'try:' in code and 'except' in code,
        'numeric-algorithm-misuse': 'return ' in code and ('%' in code or '//' in code),
        'two-pointer-misuse': 'left' in code and 'right' in code,
        'sliding-window-misuse': 'left' in code and ('for ' in code or 'right' in code),
        'greedy-choice-misuse': 'sorted(' in code or 'min(' in code or 'max(' in code,
        'backtracking-misuse': 'def ' in code and ('backtrack' in code or 'return ' in code),
    }
    if misconception_code in generic_rules:
        concept = next(
            (
                name for name, terms_for_concept in GENERIC_CONCEPT_TERMS.items()
                if _contains_term(text, terms_for_concept)
            ),
            None,
        )
        explains_action = _contains_term(text, tuple(action_terms or ()))
        return not (generic_rules[misconception_code] and concept and explains_action)
    return transfer_repeats_loop_value_misconception(
        source_code=source_code,
        reasoning=reasoning,
        action_terms=action_terms,
    )
