from copy import deepcopy

from .teach_back_rubric import LOOP_VALUES_TEACH_BACK_RUBRIC


def _teach_back_rubric(*, operation_terms, operation_description):
    rubric = deepcopy(LOOP_VALUES_TEACH_BACK_RUBRIC)
    correction = next(item for item in rubric['criteria'] if item['id'] == 'explain_correction')
    correction['meaning'] = (
        f'Explains that each current value is {operation_description} before being collected.'
    )
    correction['required_groups'][1] = list(operation_terms) + [
        'transform', 'append', 'collect', 'biến đổi', 'thêm',
    ]
    correction['feedback'] = (
        f'The correction does not specify how each current value is {operation_description}.'
    )
    return rubric


def _specialized_rubric(*, concept, operation, action_terms, diagnosis,
                        diagnosis_hints, diagnosis_answer, criteria,
                        misconception_code, misconception_indicators,
                        teach_back_followups, teach_back_answer):
    return {
        'concept': concept,
        'operation': operation,
        'requires_transfer': True,
        'allowed_misconception_codes': [misconception_code],
        'diagnosis_action_terms': action_terms,
        'diagnosis': {
            'question': diagnosis,
            'hints': diagnosis_hints,
            'answer': diagnosis_answer,
        },
        'revision_hints': [
            diagnosis,
            diagnosis_hints['2'],
            diagnosis_hints['3'],
            diagnosis_hints['4'],
        ],
        'revision_solution': teach_back_answer,
        'teach_back': {
            'criteria': criteria,
            'misconceptions': [{
                'code': misconception_code,
                'fields': ['correction', 'concept'],
                'indicators': misconception_indicators,
                'feedback': 'The explanation still uses the wrong structure or operation.',
                'follow_up_question': 'Which structure or rule should be used for this task?',
            }],
        },
        'teach_back_followups': teach_back_followups,
        'teach_back_answer': teach_back_answer,
    }


DICTIONARY_RUBRIC = _specialized_rubric(
    concept='dictionary_keys', operation='looked up by key',
    action_terms=['key', 'lookup', 'get', 'dictionary', 'value'],
    diagnosis='How does a dictionary find the value for one student name, and what happens when the name is missing?',
    diagnosis_hints={
        '2': 'A dictionary stores values under keys. Which input is the key?',
        '3': 'Which dictionary operation retrieves the value for the key "Mina"?',
        '4': 'Which safe lookup supplies a fallback when the key is absent?',
    },
    diagnosis_answer='The student name is the dictionary key. Use a safe key lookup and 0 as the fallback when it is absent.',
    criteria=[
        {'id': 'identify_original_issue', 'field': 'original_issue', 'required_for_clear': False,
         'meaning': 'Identifies confusing a dictionary key with another access pattern.',
         'required_groups': [['key', 'name', 'student', 'dictionary']],
         'feedback': 'What did the original access treat the student name as?',
         'follow_up_question': 'What did the original access treat the student name as?'},
        {'id': 'explain_failure_reason', 'field': 'failure_reason', 'required_for_clear': True,
         'meaning': 'Explains that a missing dictionary key needs a safe fallback.',
         'required_groups': [['key', 'name', 'student'], ['missing', 'absent', 'fallback', 'default', '0']],
         'feedback': 'Explain what happens when the requested dictionary key is missing.',
         'follow_up_question': 'What should happen when the requested dictionary key is missing?'},
        {'id': 'explain_correction', 'field': 'correction', 'required_for_clear': True,
         'meaning': 'Explains using a dictionary key lookup with a fallback.',
         'required_groups': [['key', 'name', 'student'], ['get', 'lookup', 'return', 'value', 'fallback']],
         'feedback': 'Explain how the correction looks up the key and returns its value.',
         'follow_up_question': 'How does the correction look up the key and return a safe value?'},
        {'id': 'name_underlying_concept', 'field': 'concept', 'required_for_clear': True,
         'meaning': 'Understands dictionary key-to-value mapping.',
         'required_groups': [['dictionary', 'mapping'], ['key'], ['value', 'associated', 'stored']],
         'feedback': 'Connect the key to the value stored in the dictionary.',
         'follow_up_question': 'In a dictionary, how is a key connected to its value?'},
        {'id': 'explain_prevention', 'field': 'prevention', 'required_for_clear': False,
         'meaning': 'Suggests checking present and missing keys.',
         'required_groups': [['test', 'check', 'try'], ['missing', 'present', 'key']],
         'feedback': 'Give one check for both present and missing keys.',
         'follow_up_question': 'Which two key cases will you test next time?'},
    ],
    misconception_code='dictionary-key-misuse',
    misconception_indicators=['use the name as a list index', 'dictionary uses positions', 'key is an index'],
    teach_back_followups={
        '2': 'What input is the dictionary key in this exercise?',
        '3': 'What value should a safe lookup return when that key is missing?',
        '4': 'Which dictionary operation can provide that fallback value?',
    },
    teach_back_answer='A student name is a dictionary key. A safe key lookup returns its associated value and uses 0 when the key is missing.',
)


FUNCTION_RUBRIC = _specialized_rubric(
    concept='function_parameters_and_return', operation='checked and returned',
    action_terms=['parameter', 'argument', 'divide', 'return', 'zero', 'fallback', 'function'],
    diagnosis='Which parameter can make the division unsafe, and what should the function return in that case?',
    diagnosis_hints={
        '2': 'A function receives inputs through parameters. Which input can be zero?',
        '3': 'What result should the function return instead of dividing by zero?',
        '4': 'If the denominator is zero, what should be returned before dividing?',
    },
    diagnosis_answer='The denominator parameter can be zero. Check it first, return 0 for that case, and otherwise return the division result.',
    criteria=[
        {'id': 'identify_original_issue', 'field': 'original_issue', 'required_for_clear': False,
         'meaning': 'Identifies the unsafe or missing parameter check.', 'required_groups': [['parameter', 'argument', 'denominator', 'input']],
         'feedback': 'Which input made the original function unsafe?', 'follow_up_question': 'Which input made the original function unsafe?'},
        {'id': 'explain_failure_reason', 'field': 'failure_reason', 'required_for_clear': True,
         'meaning': 'Explains why zero must be handled before division.', 'required_groups': [['zero', 'denominator'], ['error', 'unsafe', 'divide', 'division']],
         'feedback': 'Explain why the zero denominator needs a separate case.', 'follow_up_question': 'Why does a zero denominator need a separate case?'},
        {'id': 'explain_correction', 'field': 'correction', 'required_for_clear': True,
         'meaning': 'Explains the conditional return and normal division.', 'required_groups': [['if', 'check', 'when'], ['return', '0', 'fallback'], ['divide', '/', 'division']],
         'feedback': 'Explain both branches of the corrected function.', 'follow_up_question': 'What does the function return in each denominator case?'},
        {'id': 'name_underlying_concept', 'field': 'concept', 'required_for_clear': True,
         'meaning': 'Understands parameters and return values.', 'required_groups': [['function', 'parameter', 'argument'], ['return', 'output', 'result']],
         'feedback': 'Connect the function parameters to its returned result.', 'follow_up_question': 'How do parameters and return values work together here?'},
        {'id': 'explain_prevention', 'field': 'prevention', 'required_for_clear': False,
         'meaning': 'Suggests testing zero and ordinary inputs.', 'required_groups': [['test', 'check', 'try'], ['zero', 'normal', 'ordinary']],
         'feedback': 'Name a boundary case to test.', 'follow_up_question': 'Which boundary input will you test next time?'},
    ],
    misconception_code='function-parameter-misuse',
    misconception_indicators=['divide by zero without checking', 'ignore the denominator', 'return the parameter itself'],
    teach_back_followups={
        '2': 'Which parameter can be zero?',
        '3': 'What should the function return for a zero denominator?',
        '4': 'What should it return for a non-zero denominator?',
    },
    teach_back_answer='The denominator is a parameter that may be zero. The function checks it, returns 0 for zero, and otherwise returns the division result.',
)


LIST_INDEX_RUBRIC = _specialized_rubric(
    concept='list_indexing', operation='retrieved by index',
    action_terms=['index', 'position', 'first', 'item', 'list', 'return'],
    diagnosis='How does a list identify its first item, and what should happen when the list is empty?',
    diagnosis_hints={
        '2': 'A list uses positions called indexes. Which index identifies the first item?',
        '3': 'What should the function return when there is no first item?',
        '4': 'If the list is empty, what should be returned before reading index 0?',
    },
    diagnosis_answer='The first item is at index 0. Check for an empty list first and return None when there is no item.',
    criteria=[
        {'id': 'identify_original_issue', 'field': 'original_issue', 'required_for_clear': False,
         'meaning': 'Identifies an incorrect index or missing empty check.', 'required_groups': [['index', 'position', 'first'], ['empty', 'wrong', 'missing']],
         'feedback': 'Which index or boundary case was incorrect?', 'follow_up_question': 'Which index or boundary case was incorrect?'},
        {'id': 'explain_failure_reason', 'field': 'failure_reason', 'required_for_clear': True,
         'meaning': 'Explains zero-based indexing and the empty boundary.', 'required_groups': [['index', 'position', '0', 'zero'], ['empty', 'missing', 'error']],
         'feedback': 'Explain the first index and the empty-list case.', 'follow_up_question': 'What is the first index, and what happens for an empty list?'},
        {'id': 'explain_correction', 'field': 'correction', 'required_for_clear': True,
         'meaning': 'Explains checking empty input before reading index 0.', 'required_groups': [['if', 'check', 'when'], ['index 0', 'items[0]', 'first'], ['return', 'none', 'item']],
         'feedback': 'Explain the boundary check and the index used.', 'follow_up_question': 'How does the correction safely read the first item?'},
        {'id': 'name_underlying_concept', 'field': 'concept', 'required_for_clear': True,
         'meaning': 'Understands list indexes and positions.', 'required_groups': [['list', 'sequence'], ['index', 'position'], ['item', 'element', 'value']],
         'feedback': 'Connect the list position to its item.', 'follow_up_question': 'How does a list index identify an item?'},
        {'id': 'explain_prevention', 'field': 'prevention', 'required_for_clear': False,
         'meaning': 'Suggests testing empty and non-empty lists.', 'required_groups': [['test', 'check', 'try'], ['empty', 'one item', 'non-empty']],
         'feedback': 'Name an empty-list boundary test.', 'follow_up_question': 'Which empty-list case will you test next time?'},
    ],
    misconception_code='list-index-misuse',
    misconception_indicators=['first item is items[1]', 'index 1 is the first item', 'lists start at 1'],
    teach_back_followups={
        '2': 'Which index identifies the first list item?',
        '3': 'What should happen when the list has no items?',
        '4': 'Which check must happen before reading index 0?',
    },
    teach_back_answer='Lists are zero-indexed, so the first item is at index 0. Check for an empty list before reading it and return None when empty.',
)


def _entry(*, slug, order, title, prompt, starter_code, public_description,
           public_test_ids, hidden_test_ids, operation, operation_terms,
           diagnosis_question, diagnosis_hints, diagnosis_answer, revision_hints,
           revision_solution, teach_back_answer, transfer, active=True,
           rubric_override=None):
    return {
        'slug': slug,
        'display_order': order,
        'active': active,
        'title': title,
        'prompt': prompt,
        'starter_code': starter_code,
        'public_test_description': public_description,
        'public_test_ids': public_test_ids,
        'hidden_test_ids': hidden_test_ids,
        'operation': operation,
        'rubric': rubric_override or {
            'concept': 'loop_values',
            'operation': operation,
            'requires_transfer': True,
            'allowed_misconception_codes': ['loop-value-misuse'],
            'diagnosis_action_terms': operation_terms,
            'diagnosis': {
                'question': diagnosis_question,
                'hints': diagnosis_hints,
                'answer': diagnosis_answer,
            },
            'revision_hints': revision_hints,
            'revision_solution': revision_solution,
            'teach_back': _teach_back_rubric(
                operation_terms=operation_terms,
                operation_description=operation,
            ),
            'teach_back_followups': {
                '2': 'The loop variable holds one current item; what required operation happens before it is stored?',
                '3': 'If `colour` is one item in `for colour in colours`, what does the loop variable hold here?',
                '4': 'Complete the idea: take one current item, apply the required operation, then ___ it; what fills the blank?',
            },
            'teach_back_answer': teach_back_answer,
        },
        'transfer': transfer,
    }


CODING_CATALOG = (
    _entry(
        slug='lookup-dictionary-grade', order=4,
        title='Look up a dictionary value',
        prompt='Write a function that returns a student grade by name, or 0 when the name is missing.',
        starter_code='def lookup_grade(grades, student_name):\n    return 0',
        public_description="lookup_grade({'Aki': 92, 'Mina': 85}, 'Mina') should return 85.",
        public_test_ids=['lookup-public'], hidden_test_ids=['lookup-missing-key', 'lookup-other-key'],
        operation='looked up by key', operation_terms=['key', 'lookup', 'get', 'dictionary', 'value'],
        diagnosis_question='How does a dictionary identify the value for one student name, and what happens when that name is missing?',
        diagnosis_hints={
            '2': 'A dictionary stores values under keys. Which input is the key?',
            '3': 'Which dictionary operation retrieves the value for the key "Mina"?',
            '4': 'Use the student name as a key, then which operation safely retrieves the value?',
        },
        diagnosis_answer='The student name is the dictionary key. Use a safe lookup and 0 as the fallback when the key is absent.',
        revision_hints=[
            'Which argument identifies the student to find?',
            'Which data structure should treat the student name as a key rather than a list index?',
            'A missing key should produce 0; which lookup supports that?',
            'Which safe dictionary operation completes `return grades.____(student_name, 0)`?',
        ],
        revision_solution='Use `return grades.get(student_name, 0)`: the name is a dictionary key and get supplies 0 when absent.',
        teach_back_answer='The student name is a dictionary key rather than a numeric list index. A safe key lookup supplies 0 when missing.',
        transfer={
            'title': 'Look up a dictionary price transfer check',
            'prompt': 'Return the price for a product name, or -1 when the product is missing.',
            'test_ids': ['price-public', 'price-missing', 'price-other'],
            'action_terms': ['key', 'lookup', 'get', 'dictionary', 'value', 'fallback'],
        },
        rubric_override=DICTIONARY_RUBRIC,
    ),
    _entry(
        slug='double-numbers',
        order=1,
        title='Double every number',
        prompt='Write a function that returns a new list containing twice each input number.',
        starter_code=(
            'def double_numbers(numbers):\n'
            '    result = []\n'
            '    # Add your loop here\n'
            '    return result'
        ),
        public_description='double_numbers([1, 3]) should return [2, 6].',
        public_test_ids=['double-public'],
        hidden_test_ids=['empty-list', 'negative-values'],
        operation='doubled',
        operation_terms=['double', 'doubled', 'doubling', 'multiply', '* 2', 'times two'],
        diagnosis_question=(
            'Inside the loop, which single value should be doubled, and when should it be '
            'added to the result list?'
        ),
        diagnosis_hints={
            '2': 'The loop variable is one current number; which current number must be doubled?',
            '3': 'If `colour` is one item in `for colour in colours`, what is `number` in your number loop?',
            '4': 'Complete the idea: take the current number, ___ it, then append it; what fills the blank?',
        },
        diagnosis_answer=(
            'The loop variable holds one current number during each iteration. Double that '
            'number and append the doubled value before moving to the next item.'
        ),
        revision_hints=[
            'Which value changes on each pass through the loop?',
            'A loop processes one item at a time; which variable represents that current item?',
            'In `for colour in colours`, `colour` is one item; which variable has that role here?',
            'Complete `result.append(____)`; what expression doubles the current number?',
        ],
        revision_solution=(
            '```python\ndef double_numbers(numbers):\n    result = []\n'
            '    for number in numbers:\n        result.append(number * 2)\n'
            '    return result\n```\nEach current number is doubled before it is appended.'
        ),
        teach_back_answer=(
            'During each iteration the loop variable holds one current number. The correction '
            'doubles that number and appends the transformed value to a new result list.'
        ),
        transfer={
            'title': 'Word lengths transfer check',
            'prompt': 'Return the length of each word in a new list.',
            'test_ids': ['empty-words', 'mixed-word-lengths'],
            'action_terms': ['length', 'len', 'transform', 'append', 'collect'],
        },
    ),
    _entry(
        slug='square-numbers',
        order=2,
        title='Square every number',
        prompt='Write a function that returns a new list containing the square of each input number.',
        starter_code=(
            'def square_numbers(numbers):\n'
            '    result = []\n'
            '    # Add your loop here\n'
            '    return result'
        ),
        public_description='square_numbers([2, -3]) should return [4, 9].',
        public_test_ids=['square-public'],
        hidden_test_ids=['empty-square', 'zero-square'],
        operation='squared',
        operation_terms=['square', 'squared', 'squaring', '** 2', 'power of two'],
        diagnosis_question='During one iteration, which current number should be squared before it is appended?',
        diagnosis_hints={
            '2': 'The loop variable is one current number; which number must be multiplied by itself?',
            '3': 'If one current value is 3, its square is 9; what should happen to your current value?',
            '4': 'Complete the idea: append current number ___ current number; what fills the blank?',
        },
        diagnosis_answer=(
            'The loop variable holds one current number. Multiply that number by itself and '
            'append the squared result during the same iteration.'
        ),
        revision_hints=[
            'Which single number does the loop variable hold right now?',
            'A square uses one value twice; which current value should be used?',
            'For a current value of 3, the result item is 9; how is that produced?',
            'Complete `result.append(____)`; what expression squares the current number?',
        ],
        revision_solution=(
            '```python\ndef square_numbers(numbers):\n    result = []\n'
            '    for number in numbers:\n        result.append(number ** 2)\n'
            '    return result\n```\nEach current number is squared before it is appended.'
        ),
        teach_back_answer=(
            'During each iteration the loop variable holds one current number. The correction '
            'squares that number and appends the transformed value to a new list.'
        ),
        transfer={
            'title': 'Negate numbers transfer check',
            'prompt': 'Return a new list containing the negative of each input number.',
            'test_ids': ['empty-negate', 'mixed-negate'],
            'action_terms': ['negative', 'negate', 'multiply', '-1', 'transform', 'append'],
        },
    ),
    _entry(
        slug='increment-numbers',
        order=3,
        title='Increment every number',
        prompt='Write a function that returns a new list with one added to each input number.',
        starter_code=(
            'def increment_numbers(numbers):\n'
            '    result = []\n'
            '    # Add your loop here\n'
            '    return result'
        ),
        public_description='increment_numbers([1, 3]) should return [2, 4].',
        public_test_ids=['increment-public'],
        hidden_test_ids=['empty-increment', 'negative-increment'],
        operation='incremented',
        operation_terms=['increment', 'incremented', 'add one', '+ 1', 'plus one'],
        diagnosis_question='During one iteration, which current number should have one added before it is appended?',
        diagnosis_hints={
            '2': 'The loop variable is one current number; which number needs one added?',
            '3': 'If the current item is 3, the new item is 4; how does that map to your loop?',
            '4': 'Complete the idea: append current number ___ 1; what fills the blank?',
        },
        diagnosis_answer=(
            'The loop variable holds one current number. Add one to that number and append '
            'the incremented result during the same iteration.'
        ),
        revision_hints=[
            'Which single number does the loop variable hold on this pass?',
            'The result needs one more than the current item; which variable should change?',
            'For a current value of 3, the result item is 4; what operation produces it?',
            'Complete `result.append(____)`; what expression adds one to the current number?',
        ],
        revision_solution=(
            '```python\ndef increment_numbers(numbers):\n    result = []\n'
            '    for number in numbers:\n        result.append(number + 1)\n'
            '    return result\n```\nOne is added to each current number before it is appended.'
        ),
        teach_back_answer=(
            'During each iteration the loop variable holds one current number. The correction '
            'adds one to that number and appends the transformed value to a new list.'
        ),
        transfer={
            'title': 'Absolute values transfer check',
            'prompt': 'Return a new list containing the absolute value of each input number.',
            'test_ids': ['empty-absolute', 'mixed-absolute'],
            'action_terms': ['absolute', 'abs', 'transform', 'append', 'collect'],
        },
    ),
    _entry(
        slug='safe-divide-function', order=5,
        title='Handle a zero denominator',
        prompt='Write a function that returns a divided by b, or 0 when b is zero.',
        starter_code='def safe_divide(a, b):\n    # Check the denominator before dividing\n    return 0',
        public_description='safe_divide(6, 3) should return 2.',
        public_test_ids=['divide-public'], hidden_test_ids=['divide-by-zero', 'divide-negative'],
        operation='checked and returned', operation_terms=['parameter', 'argument', 'divide', 'return', 'zero', 'function'],
        diagnosis_question='Which parameter can make the division unsafe, and what should the function return in that case?',
        diagnosis_hints={'2': 'Which input can be zero?', '3': 'What should be returned instead of dividing by zero?', '4': 'If the denominator is zero, what should be returned before dividing?'},
        diagnosis_answer='The denominator can be zero. Check it first, return 0 for that case, and otherwise return the division result.',
        revision_hints=['Which parameter is the denominator?', 'What boundary value must be checked before division?', 'What fallback should the zero case return?', 'Which conditional returns the division only for a non-zero denominator?'],
        revision_solution='Use `if b == 0: return 0` and otherwise return `a / b`.',
        teach_back_answer='The denominator parameter may be zero. Check it, return 0 for zero, and otherwise return the division result.',
        transfer={'title': 'Safe percentage transfer check', 'prompt': 'Return part / total * 100, or 0 when total is zero.', 'test_ids': ['percentage-public', 'percentage-zero', 'percentage-other'], 'action_terms': ['parameter', 'argument', 'zero', 'return', 'divide', 'function']},
        rubric_override=FUNCTION_RUBRIC,
    ),
    _entry(
        slug='first-list-item', order=6,
        title='Read the first list item safely',
        prompt='Write a function that returns the first item in a list, or None when the list is empty.',
        starter_code='def first_item(items):\n    # Check the list before reading index 0\n    return None',
        public_description='first_item([4, 8]) should return 4.',
        public_test_ids=['first-item-public'], hidden_test_ids=['first-item-empty', 'first-item-single'],
        operation='retrieved by index', operation_terms=['index', 'position', 'first', 'item', 'list', 'return'],
        diagnosis_question='How does a list identify its first item, and what happens when the list is empty?',
        diagnosis_hints={'2': 'Which index identifies the first item?', '3': 'What should be returned when there is no item?', '4': 'If the list is empty, what should be returned before reading index 0?'},
        diagnosis_answer='The first item is at index 0. Check for an empty list first and return None when there is no item.',
        revision_hints=['Which index is the first list position?', 'What boundary case has no index 0?', 'What fallback should an empty list return?', 'Which check must happen before reading items[0]?'],
        revision_solution='Use `if not items: return None` and otherwise return `items[0]`.',
        teach_back_answer='Lists start at index 0. Check for an empty list before reading items[0], and return None when empty.',
        transfer={'title': 'Read the last list item transfer check', 'prompt': 'Return the last item in a list, or None when empty.', 'test_ids': ['last-item-public', 'last-item-empty', 'last-item-other'], 'action_terms': ['index', 'position', 'last', 'item', 'list', 'return']},
        rubric_override=LIST_INDEX_RUBRIC,
    ),
)
