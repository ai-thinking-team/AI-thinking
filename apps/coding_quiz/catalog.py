from copy import deepcopy

from runner_service.bulk_practice import BULK_SERIES, PRACTICE_LEVELS
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
                        mastery_recommendation, teach_back_followups,
                        teach_back_answer):
    return {
        'concept': concept,
        'operation': operation,
        'requires_transfer': True,
        'allowed_misconception_codes': [misconception_code],
        'mastery_recommendations': {
            misconception_code: mastery_recommendation,
        },
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
    mastery_recommendation=(
        'Review dictionary key lookups and missing-key fallbacks, then retry the '
        'dictionary price Transfer Check.'
    ),
    teach_back_followups={
        '2': 'What input is the dictionary key in this exercise?',
        '3': 'What value should a safe lookup return when that key is missing?',
        '4': 'Which dictionary operation can provide that fallback value?',
    },
    teach_back_answer='A student name is a dictionary key. A safe key lookup returns its associated value and uses 0 when the key is missing.',
)


# Additional curated practice by Python topic. Each item keeps an independent
# Transfer Check so learners cannot earn mastery by only repeating the source task.
ADDITIONAL_CODING_CATALOG = lambda: (
    _generic_topic_entry(
        slug='classify-number', order=7, title='Classify a number with if-else',
        prompt='Write a function that returns "positive", "zero", or "negative" for a number.',
        starter_code='def classify_number(number):\n    # Use if-elif-else\n    return ""',
        public_description='classify_number(4) should return "positive".',
        public_test_ids=['classify-number-public'], hidden_test_ids=['classify-number-zero', 'classify-number-negative'],
        concept='conditionals', misconception_code='if-else-branch-misuse',
        concept_terms=['if', 'else', 'condition', 'branch'], action_terms=['positive', 'zero', 'negative', 'return'],
        diagnosis='Which condition decides whether the number is positive, zero, or negative?',
        diagnosis_hints={'2': 'Which comparison identifies a positive number?', '3': 'What separate condition identifies zero?', '4': 'Which branch handles every remaining negative number?'},
        diagnosis_answer='Check whether the number is greater than zero, equal to zero, or otherwise negative.',
        revision_hints=['Which comparison should the first if statement make?', 'Which branch returns the word positive?', 'What exact condition identifies zero?', 'Which final else branch returns negative?'],
        revision_solution='Use if number > 0, elif number == 0, and else to return the three labels.',
        teach_back_answer='An if-elif-else chain checks one condition at a time and returns the label for the matching branch.',
        transfer={'title': 'Even-number Transfer Check', 'prompt': 'Return True when a number is even and False otherwise.', 'test_ids': ['is-even-true', 'is-even-false', 'is-even-zero'], 'action_terms': ['if', 'condition', 'even', 'return']},
        recommendation='Review if-elif-else branch order, then retry a new conditional exercise.',
    ),
    _generic_topic_entry(
        slug='rectangle-area', order=8, title='Create a rectangle-area function',
        prompt='Write a function that returns the area of a rectangle from its width and height.',
        starter_code='def rectangle_area(width, height):\n    return 0',
        public_description='rectangle_area(3, 4) should return 12.',
        public_test_ids=['rectangle-area-public'], hidden_test_ids=['rectangle-area-zero', 'rectangle-area-other'],
        concept='function_basics', misconception_code='function-return-misuse',
        concept_terms=['function', 'parameter', 'return'], action_terms=['width', 'height', 'multiply', 'area', 'return'],
        diagnosis='Which parameters does the function use to calculate and return the area?',
        diagnosis_hints={'2': 'Which two inputs are the rectangle dimensions?', '3': 'Which arithmetic operation combines width and height?', '4': 'What expression should the return statement give back?'},
        diagnosis_answer='Use the width and height parameters, multiply them, and return the resulting area.',
        revision_hints=['Which names receive the width and height arguments?', 'What does width multiplied by height represent?', 'Which line should return the calculated area?', 'What expression belongs after return?'],
        revision_solution='Return width * height so the function gives back the rectangle area.',
        teach_back_answer='A function receives width and height as parameters, calculates their product, and returns that area.',
        transfer={'title': 'Rectangle perimeter Transfer Check', 'prompt': 'Write a function that returns a rectangle perimeter from width and height.', 'test_ids': ['rectangle-perimeter-public', 'rectangle-perimeter-zero', 'rectangle-perimeter-other'], 'action_terms': ['function', 'parameter', 'return', 'perimeter']},
        recommendation='Review function parameters and return values, then retry a new function exercise.',
    ),
    _generic_topic_entry(
        slug='sum-one-dimensional-list', order=9, title='Sum a one-dimensional list',
        prompt='Write a function that returns the total of every number in a one-dimensional list.',
        starter_code='def sum_numbers(numbers):\n    total = 0\n    # Add each number\n    return total',
        public_description='sum_numbers([2, 3, 4]) should return 9.',
        public_test_ids=['sum-list-public'], hidden_test_ids=['sum-list-empty', 'sum-list-negative'],
        concept='list_1d_operations', misconception_code='one-dimensional-list-misuse',
        concept_terms=['list', 'element', 'number'], action_terms=['loop', 'total', 'add', 'return'],
        diagnosis='How should each number in the list change the running total?',
        diagnosis_hints={'2': 'Which variable should start at zero?', '3': 'What does the loop variable represent in one pass?', '4': 'Which addition updates the running total?'},
        diagnosis_answer='Start a total at zero, visit each list element, add it to the total, and return the total.',
        revision_hints=['Which variable stores the running total?', 'How does the loop visit one number at a time?', 'What should total become after seeing one number?', 'Which expression adds the current number to total?'],
        revision_solution='Start total at 0, add every current number during the loop, then return total.',
        teach_back_answer='A one-dimensional list contains individual elements. The loop adds each current number to one running total.',
        transfer={'title': 'Count positive numbers Transfer Check', 'prompt': 'Return how many numbers in a list are greater than zero.', 'test_ids': ['count-positive-public', 'count-positive-none', 'count-positive-mixed'], 'action_terms': ['list', 'loop', 'count', 'positive']},
        recommendation='Review one-dimensional list traversal and running totals, then retry a list exercise.',
    ),
    _generic_topic_entry(
        slug='matrix-total', order=10, title='Sum a two-dimensional list',
        prompt='Write a function that returns the total of all numbers in a two-dimensional list.',
        starter_code='def matrix_total(matrix):\n    total = 0\n    # Visit each row and value\n    return total',
        public_description='matrix_total([[1, 2], [3, 4]]) should return 10.',
        public_test_ids=['matrix-total-public'], hidden_test_ids=['matrix-total-empty', 'matrix-total-uneven'],
        concept='list_2d_traversal', misconception_code='two-dimensional-list-misuse',
        concept_terms=['matrix', 'row', 'list'], action_terms=['nested loop', 'value', 'total', 'add'],
        diagnosis='How do the outer and inner loops reach every value in the matrix?',
        diagnosis_hints={'2': 'What does one item in the outer loop represent?', '3': 'What does the inner loop visit inside one row?', '4': 'Which value should be added to total in the inner loop?'},
        diagnosis_answer='The outer loop visits each row and the inner loop visits every value in that row before adding it to total.',
        revision_hints=['Which loop variable should represent one row?', 'Which second loop reads values inside that row?', 'Where should total be updated?', 'Which current value is added to total?'],
        revision_solution='Use a loop for each row and a nested loop for each value, adding every value to total.',
        teach_back_answer='A two-dimensional list is made of rows. Nested loops visit each row and then each value inside it.',
        transfer={'title': 'Count non-zero matrix values Transfer Check', 'prompt': 'Return the number of non-zero values in a two-dimensional list.', 'test_ids': ['matrix-nonzero-public', 'matrix-nonzero-empty', 'matrix-nonzero-mixed'], 'action_terms': ['matrix', 'row', 'nested loop', 'count']},
        recommendation='Review rows and nested loops in two-dimensional lists, then retry a matrix exercise.',
    ),
    _generic_topic_entry(
        slug='reverse-string', order=11, title='Reverse a string',
        prompt='Write a function that returns the characters of a string in reverse order.',
        starter_code='def reverse_text(text):\n    return ""',
        public_description='reverse_text("cat") should return "tac".',
        public_test_ids=['reverse-string-public'], hidden_test_ids=['reverse-string-empty', 'reverse-string-unicode'],
        concept='string_operations', misconception_code='string-operation-misuse',
        concept_terms=['string', 'character', 'text'], action_terms=['reverse', 'slice', 'return'],
        diagnosis='Which string operation returns the characters in reverse order?',
        diagnosis_hints={'2': 'What kind of value is text in this function?', '3': 'Which slice step reads a string backwards?', '4': 'What expression should the function return?'},
        diagnosis_answer='Text is a string, and the slice text[::-1] returns its characters in reverse order.',
        revision_hints=['Which parameter holds the string?', 'What does a negative slice step do?', 'How can text[::-1] change the character order?', 'Which expression should return the reversed text?'],
        revision_solution='Return text[::-1] to create a reversed string.',
        teach_back_answer='A string is an ordered sequence of characters. A slice with step -1 reads those characters in reverse order.',
        transfer={'title': 'Uppercase string Transfer Check', 'prompt': 'Write a function that returns a string in uppercase.', 'test_ids': ['uppercase-string-public', 'uppercase-string-empty', 'uppercase-string-mixed'], 'action_terms': ['string', 'uppercase', 'return']},
        recommendation='Review string operations and character order, then retry a string exercise.',
    ),
    _generic_topic_entry(
        slug='triple-numbers', order=12, title='Triple every number',
        prompt='Write a function that returns a new list with every input number multiplied by three.',
        starter_code='def triple_numbers(numbers):\n    result = []\n    return result',
        public_description='triple_numbers([1, 3]) should return [3, 9].',
        public_test_ids=['triple-numbers-public'], hidden_test_ids=['triple-numbers-empty', 'triple-numbers-negative'],
        concept='loop_values', misconception_code='loop-value-misuse',
        concept_terms=['loop', 'current', 'value'], action_terms=['triple', 'multiply', 'append'],
        diagnosis='Which current value should be multiplied by three before it is appended?',
        diagnosis_hints={'2': 'What does the loop variable represent on one pass?', '3': 'Which operation changes one current number into its triple?', '4': 'Which expression should be appended to result?'},
        diagnosis_answer='The loop variable holds one current number. Multiply that number by three and append the result.',
        revision_hints=['Which current number does the loop hold?', 'What operation makes that one number triple?', 'Where should the transformed value be collected?', 'Which expression belongs inside result.append?' ],
        revision_solution='Loop over each number and append number * 3 to a new result list.',
        teach_back_answer='Each loop iteration has one current value. The correction triples that value before appending it to the result list.',
        transfer={'title': 'Add five to every number Transfer Check', 'prompt': 'Return a new list with five added to every input number.', 'test_ids': ['add-five-public', 'add-five-empty', 'add-five-negative'], 'action_terms': ['loop', 'current', 'add', 'append']},
        recommendation='Review how a loop transforms one current value at a time, then retry a loop exercise.',
    ),
    _generic_topic_entry(
        slug='factorial-recursion', order=13, title='Calculate factorial with recursion',
        prompt='Write a recursive function that returns n factorial for a non-negative integer n.',
        starter_code='def factorial(n):\n    # Add a base case and recursive case\n    return 1',
        public_description='factorial(4) should return 24.',
        public_test_ids=['factorial-public'], hidden_test_ids=['factorial-zero', 'factorial-one'],
        concept='recursion', misconception_code='recursion-base-case-misuse',
        concept_terms=['recursion', 'base case', 'function'], action_terms=['call', 'n - 1', 'multiply', 'return'],
        diagnosis='Which base case stops factorial recursion and which smaller call continues it?',
        diagnosis_hints={'2': 'What should factorial return when n is zero?', '3': 'How should n change in the recursive call?', '4': 'Which multiplication combines n with the smaller factorial?'},
        diagnosis_answer='The base case returns 1 for n equal to zero. Otherwise return n multiplied by factorial of n minus one.',
        revision_hints=['Which input should stop the recursive calls?', 'What value does the base case return?', 'Which smaller argument should factorial call next?', 'How does n multiply the recursive result?'],
        revision_solution='Return 1 when n is 0; otherwise return n * factorial(n - 1).',
        teach_back_answer='Recursion needs a base case to stop. The recursive case reduces n and combines n with the result of the smaller call.',
        transfer={'title': 'Sum to n Transfer Check', 'prompt': 'Write a recursive function that returns 1 + 2 + ... + n for n greater than or equal to zero.', 'test_ids': ['sum-to-n-public', 'sum-to-n-zero', 'sum-to-n-other'], 'action_terms': ['recursion', 'base case', 'n - 1', 'return']},
        recommendation='Review recursive base cases and smaller recursive calls, then retry a recursion exercise.',
    ),
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
    mastery_recommendation=(
        'Review denominator checks and conditional return values, then retry the '
        'safe percentage Transfer Check.'
    ),
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
    mastery_recommendation=(
        'Review zero-based indexing and empty-list boundary checks, then retry the '
        'last-item Transfer Check.'
    ),
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
            'mastery_recommendations': {
                'loop-value-misuse': (
                    'Review how a loop transforms one current item at a time, then retry '
                    'the parallel Transfer Check.'
                ),
            },
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


def _generic_topic_rubric(*, concept, misconception_code, concept_terms, action_terms,
                          diagnosis, diagnosis_hints, diagnosis_answer,
                          revision_hints, revision_solution, teach_back_answer,
                          recommendation):
    """Create a complete rubric for a curated beginner-Python concept family."""
    return _specialized_rubric(
        concept=concept,
        operation=', '.join(action_terms[:2]),
        action_terms=action_terms,
        diagnosis=diagnosis,
        diagnosis_hints=diagnosis_hints,
        diagnosis_answer=diagnosis_answer,
        criteria=[
            {
                'id': 'identify_original_issue', 'field': 'original_issue',
                'required_for_clear': False,
                'meaning': 'Identifies the missed rule or boundary case.',
                'required_groups': [list(concept_terms)],
                'feedback': 'Name the rule or boundary case that the original approach missed.',
                'follow_up_question': 'Which rule or boundary case did the original approach miss?',
            },
            {
                'id': 'explain_failure_reason', 'field': 'failure_reason',
                'required_for_clear': True,
                'meaning': 'Explains why the concept and operation matter for the result.',
                'required_groups': [list(concept_terms), list(action_terms)],
                'feedback': 'Connect the concept rule to the result that the code should produce.',
                'follow_up_question': 'How does this concept rule affect the required result?',
            },
            {
                'id': 'explain_correction', 'field': 'correction',
                'required_for_clear': True,
                'meaning': 'Explains the corrected operation using the target concept.',
                'required_groups': [list(concept_terms), list(action_terms)],
                'feedback': 'Explain the corrected operation and the concept rule it follows.',
                'follow_up_question': 'Which corrected operation follows the concept rule?',
            },
            {
                'id': 'name_underlying_concept', 'field': 'concept',
                'required_for_clear': True,
                'meaning': 'Names and explains the target programming concept.',
                'required_groups': [list(concept_terms)],
                'feedback': 'Name the programming concept that makes this solution work.',
                'follow_up_question': 'Which programming concept makes the corrected solution work?',
            },
            {
                'id': 'explain_prevention', 'field': 'prevention',
                'required_for_clear': False,
                'meaning': 'Gives a concrete future test or trace.',
                'required_groups': [['test', 'check', 'trace', 'example']],
                'feedback': 'Describe one concrete test or trace for the next similar problem.',
                'follow_up_question': 'What concrete test or trace will you use next time?',
            },
        ],
        misconception_code=misconception_code,
        misconception_indicators=['the rule does not matter', 'ignore the boundary case'],
        mastery_recommendation=recommendation,
        teach_back_followups={
            '2': diagnosis_hints['2'],
            '3': diagnosis_hints['3'],
            '4': diagnosis_hints['4'],
        },
        teach_back_answer=teach_back_answer,
    )


def _generic_topic_entry(*, slug, order, title, prompt, starter_code,
                         public_description, public_test_ids, hidden_test_ids,
                         concept, misconception_code, concept_terms, action_terms,
                         diagnosis, diagnosis_hints, diagnosis_answer,
                         revision_hints, revision_solution, teach_back_answer,
                         transfer, recommendation):
    return _entry(
        slug=slug,
        order=order,
        title=title,
        prompt=prompt,
        starter_code=starter_code,
        public_description=public_description,
        public_test_ids=public_test_ids,
        hidden_test_ids=hidden_test_ids,
        operation=', '.join(action_terms[:2]),
        operation_terms=action_terms,
        diagnosis_question=diagnosis,
        diagnosis_hints=diagnosis_hints,
        diagnosis_answer=diagnosis_answer,
        revision_hints=revision_hints,
        revision_solution=revision_solution,
        teach_back_answer=teach_back_answer,
        transfer=transfer,
        rubric_override=_generic_topic_rubric(
            concept=concept,
            misconception_code=misconception_code,
            concept_terms=concept_terms,
            action_terms=action_terms,
            diagnosis=diagnosis,
            diagnosis_hints=diagnosis_hints,
            diagnosis_answer=diagnosis_answer,
            revision_hints=revision_hints,
            revision_solution=revision_solution,
            teach_back_answer=teach_back_answer,
            recommendation=recommendation,
        ),
    )


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

CODING_CATALOG += ADDITIONAL_CODING_CATALOG()


DSA_CODING_CATALOG = (
    _generic_topic_entry(
        slug='binary-search-index', order=14, title='Find an index with binary search',
        prompt='Write a function that returns the index of target in a sorted list, or -1 when target is absent.',
        starter_code='def binary_search(numbers, target):\n    left = 0\n    right = len(numbers) - 1\n    return -1',
        public_description='binary_search([1, 3, 5, 7], 5) should return 2.',
        public_test_ids=['binary-search-public'], hidden_test_ids=['binary-search-missing', 'binary-search-single'],
        concept='binary_search', misconception_code='binary-search-boundary-misuse',
        concept_terms=['binary search', 'middle', 'sorted'], action_terms=['left', 'right', 'middle', 'target'],
        diagnosis='How should the left and right boundaries change after comparing the middle value with target?',
        diagnosis_hints={'2': 'Which index is halfway between left and right?', '3': 'Which boundary moves when the middle value is too small?', '4': 'What should the function return when the boundaries cross?'},
        diagnosis_answer='Check the middle index. Move left rightward when its value is too small, move right leftward when it is too large, and return -1 after the boundaries cross.',
        revision_hints=['Which formula calculates the middle index?', 'What comparison identifies a found target?', 'When should left become middle plus one?', 'When should right become middle minus one?'],
        revision_solution='Use a while left <= right loop, compare numbers[middle], and narrow the sorted search range.',
        teach_back_answer='Binary search relies on sorted input. Each middle comparison discards half of the remaining range by moving one boundary.',
        transfer={'title': 'First greater-or-equal index Transfer Check', 'prompt': 'Return the first index whose sorted-list value is greater than or equal to target, or -1 when none exists.', 'test_ids': ['first-geq-public', 'first-geq-none', 'first-geq-duplicate'], 'action_terms': ['binary search', 'left', 'right', 'middle']},
        recommendation='Review binary-search boundaries and sorted-list invariants, then retry a search exercise.',
    ),
    _generic_topic_entry(
        slug='valid-brackets-stack', order=15, title='Validate brackets with a stack',
        prompt='Write a function that returns True when (), [], and {} brackets are correctly balanced.',
        starter_code='def valid_brackets(text):\n    stack = []\n    return True',
        public_description='valid_brackets("([])") should return True.',
        public_test_ids=['valid-brackets-public'], hidden_test_ids=['valid-brackets-unclosed', 'valid-brackets-wrong-order'],
        concept='stack', misconception_code='stack-order-misuse',
        concept_terms=['stack', 'last in', 'last out'], action_terms=['append', 'pop', 'opening', 'closing'],
        diagnosis='Why must each closing bracket match the most recently opened bracket?',
        diagnosis_hints={'2': 'Which list operation adds an opening bracket to a stack?', '3': 'Which operation reads and removes the newest opening bracket?', '4': 'What should happen if a closing bracket has no matching top item?'},
        diagnosis_answer='A stack is last-in-first-out. Append opening brackets, then pop and compare the latest opening bracket for every closing bracket.',
        revision_hints=['Which opening brackets should be appended?', 'Which closing bracket matches the stack top?', 'When is popping from an empty stack invalid?', 'What final stack state means every bracket was matched?'],
        revision_solution='Append opening brackets; for every closing bracket, pop and compare the latest opening bracket; finish with an empty stack.',
        teach_back_answer='A stack preserves nesting because the latest opening bracket must be closed first. Append pushes and pop removes that latest item.',
        transfer={'title': 'Remove adjacent duplicates Transfer Check', 'prompt': 'Use a stack to remove adjacent matching characters repeatedly, returning the remaining text.', 'test_ids': ['remove-adjacent-public', 'remove-adjacent-empty', 'remove-adjacent-chain'], 'action_terms': ['stack', 'append', 'pop', 'character']},
        recommendation='Review last-in-first-out stack order and matching the top item, then retry a stack exercise.',
    ),
    _generic_topic_entry(
        slug='rotate-queue', order=16, title='Rotate a queue',
        prompt='Write a function that moves the front item of a queue list to the back and returns the new queue.',
        starter_code='def rotate_queue(items):\n    return items',
        public_description='rotate_queue(["A", "B", "C"]) should return ["B", "C", "A"].',
        public_test_ids=['rotate-queue-public'], hidden_test_ids=['rotate-queue-empty', 'rotate-queue-single'],
        concept='queue', misconception_code='queue-order-misuse',
        concept_terms=['queue', 'front', 'back'], action_terms=['first', 'last', 'remove', 'append'],
        diagnosis='Which item leaves a queue first and where should that item be placed after rotation?',
        diagnosis_hints={'2': 'Which list position represents the front of this queue?', '3': 'Which item should become the final item after rotation?', '4': 'What should the function return for an empty queue?'},
        diagnosis_answer='A queue removes the front item first. For rotation, take the first item, keep the remaining order, and append that item at the back.',
        revision_hints=['Which position is the queue front?', 'How can the remaining items keep their order?', 'Where should the old front item be appended?', 'What boundary case has no front item?'],
        revision_solution='Return the unchanged empty list when needed; otherwise return items[1:] plus the original first item.',
        teach_back_answer='A queue is first-in-first-out. Rotation removes the front item and appends that same item at the back after the remaining queue.',
        transfer={'title': 'Read queue front Transfer Check', 'prompt': 'Return the front item of a queue, or None when the queue is empty.', 'test_ids': ['queue-front-public', 'queue-front-empty', 'queue-front-other'], 'action_terms': ['queue', 'front', 'first', 'return']},
        recommendation='Review first-in-first-out queue order and empty-queue handling, then retry a queue exercise.',
    ),
    _generic_topic_entry(
        slug='selection-sort', order=17, title='Sort numbers with selection sort',
        prompt='Write a function that returns a new list sorted from smallest to largest without changing the input list.',
        starter_code='def selection_sort(numbers):\n    result = []\n    remaining = numbers[:]\n    return result',
        public_description='selection_sort([3, 1, 2]) should return [1, 2, 3].',
        public_test_ids=['selection-sort-public'], hidden_test_ids=['selection-sort-empty', 'selection-sort-duplicates'],
        concept='sorting', misconception_code='sorting-invariant-misuse',
        concept_terms=['sort', 'smallest', 'list'], action_terms=['minimum', 'remove', 'append', 'remaining'],
        diagnosis='Which value must be selected from the remaining list on each pass?',
        diagnosis_hints={'2': 'What should the first item in an ascending result be?', '3': 'How does the remaining list change after choosing its minimum?', '4': 'Where should the chosen minimum be stored?'},
        diagnosis_answer='On each pass choose the smallest remaining value, remove it from the working list, and append it to the sorted result.',
        revision_hints=['Which value belongs next in ascending order?', 'Which list still holds values not yet selected?', 'What should happen to a selected minimum?', 'Which list receives the selected value?'],
        revision_solution='Copy the input, repeatedly remove its minimum value, and append that value to a new sorted result.',
        teach_back_answer='Selection sort maintains a sorted result and an unsorted remainder. Each pass moves the smallest remaining value into the result.',
        transfer={'title': 'Descending sort Transfer Check', 'prompt': 'Return a new list sorted from largest to smallest.', 'test_ids': ['sort-descending-public', 'sort-descending-empty', 'sort-descending-duplicates'], 'action_terms': ['sort', 'largest', 'remaining', 'append']},
        recommendation='Review sorting invariants and selecting from the remaining values, then retry a sorting exercise.',
    ),
    _generic_topic_entry(
        slug='two-sum-hash-map', order=18, title='Find two-sum indexes with a hash map',
        prompt='Return indexes of two numbers that add to target, or [-1, -1] when no pair exists.',
        starter_code='def two_sum_indexes(numbers, target):\n    seen = {}\n    return [-1, -1]',
        public_description='two_sum_indexes([2, 7, 11, 15], 9) should return [0, 1].',
        public_test_ids=['two-sum-public'], hidden_test_ids=['two-sum-duplicate', 'two-sum-missing'],
        concept='hash_maps', misconception_code='hash-map-complement-misuse',
        concept_terms=['dictionary', 'key', 'value'], action_terms=['complement', 'target', 'index', 'lookup'],
        diagnosis='What complement should be looked up before the current number is stored in the dictionary?',
        diagnosis_hints={'2': 'What number added to the current value would equal target?', '3': 'What information should the dictionary store for each seen number?', '4': 'When does a complement lookup reveal the two indexes?'},
        diagnosis_answer='For each number compute target minus that number. If the complement is already a dictionary key, return its stored index and the current index.',
        revision_hints=['What is target minus the current number?', 'Which dictionary key represents a seen number?', 'What value should that key store?', 'When should the function return two indexes?'],
        revision_solution='Look up target - number in a seen dictionary before storing number with its index.',
        teach_back_answer='A hash map gives fast lookup by key. The complement key links a current number to an earlier number that completes the target sum.',
        transfer={'title': 'First duplicate Transfer Check', 'prompt': 'Return the first value that appears twice while scanning a list, or None when every value is unique.', 'test_ids': ['first-duplicate-public', 'first-duplicate-none', 'first-duplicate-other'], 'action_terms': ['dictionary', 'set', 'lookup', 'seen']},
        recommendation='Review hash-map keys, stored values, and complement lookup, then retry a hash-map exercise.',
    ),
    _generic_topic_entry(
        slug='graph-has-path', order=19, title='Find a path in a graph',
        prompt='Write a function that returns True when a path exists from start to target in a directed adjacency-list graph.',
        starter_code='def has_path(graph, start, target):\n    return False',
        public_description='has_path({"A": ["B"], "B": ["C"], "C": []}, "A", "C") should return True.',
        public_test_ids=['graph-path-public'], hidden_test_ids=['graph-path-missing', 'graph-path-cycle'],
        concept='graphs', misconception_code='graph-visited-misuse',
        concept_terms=['graph', 'node', 'visited'], action_terms=['neighbor', 'stack', 'queue', 'search'],
        diagnosis='Why must graph search remember visited nodes while exploring neighbors?',
        diagnosis_hints={'2': 'What values are stored in each adjacency-list entry?', '3': 'Which nodes should be added after visiting one node?', '4': 'What can happen in a graph cycle without a visited set?'},
        diagnosis_answer='A graph maps each node to neighbors. Search explores neighbors while recording visited nodes so cycles do not cause repeated work forever.',
        revision_hints=['Which node should be searched first?', 'Where are its neighbors found?', 'Which set records nodes already processed?', 'When should the function return True?'],
        revision_solution='Use a stack or queue of nodes, skip visited nodes, add unseen neighbors, and return True after reaching target.',
        teach_back_answer='Graph traversal follows neighbor links. A visited set prevents cycles from revisiting nodes and lets the search terminate safely.',
        transfer={'title': 'Reachable-node count Transfer Check', 'prompt': 'Return how many nodes are reachable from start in a directed adjacency-list graph.', 'test_ids': ['reachable-count-public', 'reachable-count-isolated', 'reachable-count-cycle'], 'action_terms': ['graph', 'node', 'visited', 'neighbor']},
        recommendation='Review graph neighbors, traversal order, and visited-node tracking, then retry a graph exercise.',
    ),
    _generic_topic_entry(
        slug='climb-stairs-dp', order=20, title='Count ways to climb stairs with dynamic programming',
        prompt='Return the number of ways to climb n stairs when each move is one or two steps.',
        starter_code='def climb_stairs(n):\n    return 0',
        public_description='climb_stairs(4) should return 5; climb_stairs(0) should return 1 (the empty climb).',
        public_test_ids=['climb-stairs-public'], hidden_test_ids=['climb-stairs-zero', 'climb-stairs-other'],
        concept='dynamic_programming', misconception_code='dynamic-programming-state-misuse',
        concept_terms=['dynamic programming', 'state', 'previous'], action_terms=['one step', 'two steps', 'sum', 'base case'],
        diagnosis='Which previous stair counts must be combined to calculate the next count?',
        diagnosis_hints={'2': 'How many ways are there to climb zero stairs?', '3': 'Which two earlier counts lead to the next stair?', '4': 'How should the previous two counts update after each step?'},
        diagnosis_answer='Use base counts for zero and one stair. Each next count is the sum of the previous one-step and two-step counts.',
        revision_hints=['Which base count represents zero stairs?', 'What is the count for one stair?', 'Which two previous states are added?', 'How can two variables keep the previous counts?'],
        revision_solution='Start from the two base counts and repeatedly replace them with their sum until reaching n.',
        teach_back_answer='Dynamic programming stores smaller solved states. The number of ways for the next stair is the sum of the two previous state counts.',
        transfer={'title': 'Fibonacci number Transfer Check', 'prompt': 'Return the nth Fibonacci number with F(0) = 0 and F(1) = 1 using iterative dynamic programming.', 'test_ids': ['fibonacci-public', 'fibonacci-zero', 'fibonacci-other'], 'action_terms': ['dynamic programming', 'previous', 'sum', 'base case']},
        recommendation='Review dynamic-programming base cases and state transitions, then retry a DP exercise.',
    ),
)

CODING_CATALOG += DSA_CODING_CATALOG


# A second exercise for every topic that previously had only one.  These use
# the same concept family but a different Transfer Check, so progress remains
# evidence-based rather than a repeated copy of the source task.
SECOND_PRACTICE_CATALOG = (
    _generic_topic_entry(
        slug='is-leap-year', order=21, title='Check a leap year with if-else',
        prompt='Write a function that returns True when a year is a leap year and False otherwise.',
        starter_code='def is_leap_year(year):\n    return False',
        public_description='is_leap_year(2024) should return True.',
        public_test_ids=['leap-year-public'], hidden_test_ids=['leap-year-century', 'leap-year-four-hundred'],
        concept='conditionals', misconception_code='if-else-branch-misuse',
        concept_terms=['if', 'else', 'condition', 'branch'], action_terms=['divisible', 'year', 'return', 'condition'],
        diagnosis='Which divisibility conditions distinguish ordinary years, century years, and leap years?',
        diagnosis_hints={'2': 'Which remainder test identifies a year divisible by four hundred?', '3': 'Why does a year divisible by one hundred need a separate branch?', '4': 'Which final condition accepts years divisible by four?'},
        diagnosis_answer='A year divisible by 400 is a leap year. A year divisible by 100 is otherwise not, and other years divisible by 4 are leap years.',
        revision_hints=['Which condition must be checked first for a year divisible by 400?', 'Which branch handles years divisible by 100 but not by 400?', 'Which remaining years are divisible by 4?', 'What Boolean value should every branch return?'],
        revision_solution='Check divisibility by 400 first, then reject other multiples of 100, then accept multiples of 4.',
        teach_back_answer='The if-else branches must test the exceptional century rule before the general divisible-by-four rule.',
        transfer={'title': 'Score-label Transfer Check', 'prompt': 'Return "A" for scores at least 90, "B" for scores at least 80, and "C" otherwise.', 'test_ids': ['score-label-a', 'score-label-b', 'score-label-c'], 'action_terms': ['if', 'else', 'score', 'return']},
        recommendation='Review ordered if-else conditions and exceptional cases, then retry a conditional exercise.',
    ),
    _generic_topic_entry(
        slug='is-palindrome', order=22, title='Check whether a string is a palindrome',
        prompt='Write a function that returns True when text reads the same forward and backward.',
        starter_code='def is_palindrome(text):\n    return False',
        public_description='is_palindrome("level") should return True.',
        public_test_ids=['palindrome-public'], hidden_test_ids=['palindrome-false', 'palindrome-empty'],
        concept='string_operations', misconception_code='string-operation-misuse',
        concept_terms=['string', 'character', 'text'], action_terms=['reverse', 'compare', 'slice', 'return'],
        diagnosis='How can the original string be compared with its reversed character order?',
        diagnosis_hints={'2': 'Which parameter contains the original text?', '3': 'Which slice expression reads the characters backwards?', '4': 'Which two string values should be compared?'},
        diagnosis_answer='Reverse the text with text[::-1] and compare that reversed string with the original text.',
        revision_hints=['Which variable holds the original string?', 'Which slice reverses all characters?', 'What comparison checks that both strings are equal?', 'What Boolean result should the function return?'],
        revision_solution='Return text == text[::-1] so the original and reversed strings are compared.',
        teach_back_answer='A palindrome has the same ordered characters in both directions, so comparing the string with its reverse gives a Boolean answer.',
        transfer={'title': 'Vowel-count Transfer Check', 'prompt': 'Return how many characters in text are vowels a, e, i, o, or u, ignoring case.', 'test_ids': ['vowel-count-public', 'vowel-count-none', 'vowel-count-mixed'], 'action_terms': ['string', 'character', 'lower', 'count']},
        recommendation='Review string character order and string comparisons, then retry a string exercise.',
    ),
    _generic_topic_entry(
        slug='power-of-two-recursion', order=23, title='Calculate a power of two with recursion',
        prompt='Write a recursive function that returns 2 raised to non-negative integer n.',
        starter_code='def power_of_two(n):\n    return 1',
        public_description='power_of_two(5) should return 32.',
        public_test_ids=['power-two-public'], hidden_test_ids=['power-two-zero', 'power-two-one'],
        concept='recursion', misconception_code='recursion-base-case-misuse',
        concept_terms=['recursion', 'base case', 'function'], action_terms=['call', 'n - 1', 'multiply', 'return'],
        diagnosis='Which base case stops the recursive calls and which smaller input should the function call next?',
        diagnosis_hints={'2': 'What value is two raised to the power zero?', '3': 'How should n change in the next recursive call?', '4': 'Which multiplier combines the smaller result with the current result?'},
        diagnosis_answer='Return 1 when n is zero. Otherwise return 2 multiplied by power_of_two of n minus one.',
        revision_hints=['Which n value is the base case?', 'What should the base case return?', 'Which smaller argument must the recursive call use?', 'What multiplication combines the smaller result?'],
        revision_solution='Return 1 for n equal to zero; otherwise return 2 * power_of_two(n - 1).',
        teach_back_answer='The base case stops at zero, and every recursive call reduces n before multiplying the smaller power by two.',
        transfer={'title': 'Odd-number sum Transfer Check', 'prompt': 'Write a recursive function that returns the sum of the first n positive odd numbers.', 'test_ids': ['odd-sum-public', 'odd-sum-zero', 'odd-sum-other'], 'action_terms': ['recursion', 'base case', 'n - 1', 'sum']},
        recommendation='Review recursive base cases and decreasing inputs, then retry a recursion exercise.',
    ),
    _generic_topic_entry(
        slug='first-binary-search-index', order=24, title='Find the first matching index with binary search',
        prompt='Return the first index of target in a sorted list, or -1 when target is absent.',
        starter_code='def first_binary_search(numbers, target):\n    return -1',
        public_description='first_binary_search([1, 2, 2, 2, 3], 2) should return 1.',
        public_test_ids=['first-binary-public'], hidden_test_ids=['first-binary-missing', 'first-binary-later'],
        concept='binary_search', misconception_code='binary-search-boundary-misuse',
        concept_terms=['binary search', 'middle', 'sorted'], action_terms=['left', 'right', 'middle', 'target'],
        diagnosis='Why must the right boundary continue moving after a matching middle value is found?',
        diagnosis_hints={'2': 'Which half can still contain an earlier matching index?', '3': 'What candidate index should be remembered after a match?', '4': 'Which boundary moves leftward to find an earlier match?'},
        diagnosis_answer='Remember a matching middle index, then move the right boundary leftward because an earlier equal value may exist.',
        revision_hints=['Which variable can store the best matching index?', 'What happens when the middle value is less than target?', 'After a match, which boundary should search the earlier half?', 'When should the saved index be returned?'],
        revision_solution='Use binary search while saving a match and moving right to middle minus one until the first match is found.',
        teach_back_answer='The sorted-list invariant allows binary search to keep narrowing the range; a match is saved while the left half is searched for an earlier one.',
        transfer={'title': 'Last matching index Transfer Check', 'prompt': 'Return the last index of target in a sorted list, or -1 when target is absent.', 'test_ids': ['last-binary-public', 'last-binary-missing', 'last-binary-duplicate'], 'action_terms': ['binary search', 'left', 'right', 'middle']},
        recommendation='Review binary-search boundaries and duplicate-value handling, then retry a search exercise.',
    ),
    _generic_topic_entry(
        slug='insertion-sort', order=25, title='Sort numbers with insertion sort',
        prompt='Write a function that returns a new list sorted from smallest to largest without changing the input list.',
        starter_code='def insertion_sort(numbers):\n    result = []\n    return result',
        public_description='insertion_sort([3, 1, 2]) should return [1, 2, 3].',
        public_test_ids=['insertion-sort-public'], hidden_test_ids=['insertion-sort-empty', 'insertion-sort-duplicates'],
        concept='sorting', misconception_code='sorting-invariant-misuse',
        concept_terms=['sort', 'smallest', 'list'], action_terms=['insert', 'sorted', 'value', 'position'],
        diagnosis='Where should each new value be inserted so the growing result stays sorted?',
        diagnosis_hints={'2': 'What invariant should the result list satisfy after each insertion?', '3': 'Which existing result values should remain before a larger new value?', '4': 'What position should receive a value smaller than every result item?'},
        diagnosis_answer='Keep a sorted result list and insert each new value before the first larger result value, or at the end when none is larger.',
        revision_hints=['What property should result have before processing the next number?', 'How can a position for the new number be found?', 'Where should a smaller number be inserted?', 'What should happen when the new number is larger than every result value?'],
        revision_solution='Build a new result list and insert each input number at the first position whose value is greater than it.',
        teach_back_answer='Insertion sort maintains a sorted prefix. Each new value is placed at the position that preserves ascending order.',
        transfer={'title': 'Merge sorted lists Transfer Check', 'prompt': 'Return one ascending list formed by merging two already sorted number lists.', 'test_ids': ['merge-sorted-public', 'merge-sorted-empty', 'merge-sorted-other'], 'action_terms': ['sorted', 'smallest', 'append', 'merge']},
        recommendation='Review sorted-list invariants and insertion positions, then retry a sorting exercise.',
    ),
    _generic_topic_entry(
        slug='character-frequencies', order=26, title='Count character frequencies with a hash map',
        prompt='Return a dictionary mapping every character in text to its number of appearances.',
        starter_code='def character_frequencies(text):\n    counts = {}\n    return counts',
        public_description='character_frequencies("banana") should return {"b": 1, "a": 3, "n": 2}.',
        public_test_ids=['char-frequency-public'], hidden_test_ids=['char-frequency-empty', 'char-frequency-other'],
        concept='hash_maps', misconception_code='hash-map-complement-misuse',
        concept_terms=['dictionary', 'key', 'value'], action_terms=['character', 'count', 'key', 'update'],
        diagnosis='Which dictionary key and value should be updated for each character?',
        diagnosis_hints={'2': 'What value can identify one character in a dictionary?', '3': 'What number should be stored for each character key?', '4': 'How should an existing count change after another matching character?'},
        diagnosis_answer='Use each character as a dictionary key and increase its stored count by one while scanning the text.',
        revision_hints=['Which current value becomes a dictionary key?', 'What initial count should a new key receive?', 'How is a seen character count updated?', 'What dictionary should be returned after the loop?'],
        revision_solution='For each character, store counts[char] as its previous count plus one, then return counts.',
        teach_back_answer='A hash map stores a count under each character key, allowing one lookup and update for every character scanned.',
        transfer={'title': 'Unique-character Transfer Check', 'prompt': 'Return True when every character in text appears only once and False otherwise.', 'test_ids': ['unique-char-public', 'unique-char-false', 'unique-char-empty'], 'action_terms': ['dictionary', 'set', 'character', 'seen']},
        recommendation='Review dictionary keys and count updates, then retry a hash-map exercise.',
    ),
    _generic_topic_entry(
        slug='shortest-graph-path', order=27, title='Find the shortest path length in a graph',
        prompt='Return the fewest number of edges from start to target in a directed adjacency-list graph, or -1 when unreachable.',
        starter_code='def shortest_path_length(graph, start, target):\n    return -1',
        public_description='shortest_path_length({"A": ["B"], "B": ["C"], "C": []}, "A", "C") should return 2.',
        public_test_ids=['shortest-path-public'], hidden_test_ids=['shortest-path-missing', 'shortest-path-cycle'],
        concept='graphs', misconception_code='graph-visited-misuse',
        concept_terms=['graph', 'node', 'visited'], action_terms=['queue', 'neighbor', 'distance', 'search'],
        diagnosis='Why does a queue explore every graph distance before moving to a farther distance?',
        diagnosis_hints={'2': 'Which node and distance pair should the queue start with?', '3': 'What distance should an unseen neighbor receive?', '4': 'Which set prevents a cycle from adding the same node repeatedly?'},
        diagnosis_answer='Breadth-first search keeps node-distance pairs in a queue, adds unseen neighbors at distance plus one, and records visited nodes.',
        revision_hints=['What starting distance belongs with start?', 'Which structure removes the oldest node-distance pair first?', 'How should a neighbor distance be calculated?', 'When should the function return minus one?'],
        revision_solution='Use a queue of node-distance pairs, mark visited nodes, and return a neighbor distance when target is reached.',
        teach_back_answer='Breadth-first search visits all nodes one edge away before nodes farther away, so the first reached target has the shortest edge count.',
        transfer={'title': 'Reachable-node list Transfer Check', 'prompt': 'Return an alphabetically sorted list of all nodes reachable from start in a directed adjacency-list graph.', 'test_ids': ['reachable-list-public', 'reachable-list-isolated', 'reachable-list-cycle'], 'action_terms': ['graph', 'node', 'visited', 'neighbor']},
        recommendation='Review breadth-first graph traversal, queue order, and visited-node tracking, then retry a graph exercise.',
    ),
    _generic_topic_entry(
        slug='min-cost-climbing-stairs', order=28, title='Find minimum climbing cost with dynamic programming',
        prompt='Return the minimum cost to reach the top when cost[i] is paid to step on stair i and you may climb one or two stairs at a time.',
        starter_code='def min_cost_climbing_stairs(cost):\n    return 0',
        public_description='min_cost_climbing_stairs([10, 15, 20]) should return 15.',
        public_test_ids=['min-cost-public'], hidden_test_ids=['min-cost-empty', 'min-cost-other'],
        concept='dynamic_programming', misconception_code='dynamic-programming-state-misuse',
        concept_terms=['dynamic programming', 'state', 'previous'], action_terms=['minimum', 'cost', 'previous', 'sum'],
        diagnosis='Which two previous minimum costs must be compared before calculating the next stair cost?',
        diagnosis_hints={'2': 'What minimum costs are needed before processing the first paid stair?', '3': 'Which two previous states can reach the next stair?', '4': 'How is the smaller previous state combined with the current stair cost?'},
        diagnosis_answer='For each stair, add its cost to the smaller of the two previous minimum costs, then the top uses the smaller of the final two states.',
        revision_hints=['Which two state values should be remembered?', 'How is the next minimum cost calculated?', 'Which old state should be discarded after an update?', 'Which final two values determine the top cost?'],
        revision_solution='Iterate through costs while retaining the previous two minimum states, then return the smaller final state.',
        teach_back_answer='Dynamic programming stores the best cost for smaller stair states. Each new state chooses the cheaper of the two ways that reach it.',
        transfer={'title': 'Tribonacci Transfer Check', 'prompt': 'Return T(n) where T(0)=0, T(1)=1, T(2)=1, and every later value is the sum of the previous three.', 'test_ids': ['tribonacci-public', 'tribonacci-zero', 'tribonacci-other'], 'action_terms': ['dynamic programming', 'previous', 'state', 'sum']},
        recommendation='Review dynamic-programming state updates and choosing the best previous state, then retry a DP exercise.',
    ),
)

CODING_CATALOG += SECOND_PRACTICE_CATALOG


def _expansion_entry(*, slug, order, title, prompt, starter_code,
                     public_description, public_test_ids, hidden_test_ids,
                     concept, misconception_code, concept_terms, action_terms,
                     strategy, transfer, recommendation):
    """Keep the larger practice pack consistent with the full learning contract."""
    primary_action = action_terms[0]
    secondary_action = action_terms[1]
    return _generic_topic_entry(
        slug=slug, order=order, title=title, prompt=prompt, starter_code=starter_code,
        public_description=public_description, public_test_ids=public_test_ids,
        hidden_test_ids=hidden_test_ids, concept=concept,
        misconception_code=misconception_code, concept_terms=concept_terms,
        action_terms=action_terms,
        diagnosis=f'Which {concept_terms[0]} rule determines the correct {primary_action} step?',
        diagnosis_hints={
            '2': f'Which input or state should the {concept_terms[0]} rule inspect?',
            '3': f'How should {primary_action} change the result or state?',
            '4': f'What result should the function return after {secondary_action}?',
        },
        diagnosis_answer=strategy,
        revision_hints=[
            f'Which {concept_terms[0]} rule must the solution preserve?',
            f'What current value or state should {primary_action} use?',
            f'How should {secondary_action} update the result?',
            'Which final value should the function return?',
        ],
        revision_solution=strategy,
        teach_back_answer=strategy,
        transfer=transfer,
        recommendation=recommendation,
    )


EXPANDED_PRACTICE_CATALOG = (
    _expansion_entry(
        slug='unique-sorted-numbers', order=29, title='Return unique sorted numbers',
        prompt='Return a new ascending list containing each number only once.',
        starter_code='def unique_sorted_numbers(numbers):\n    return []',
        public_description='unique_sorted_numbers([3, 1, 3, 2]) should return [1, 2, 3].',
        public_test_ids=['unique-sorted-public'], hidden_test_ids=['unique-sorted-empty', 'unique-sorted-negative'],
        concept='set_operations', misconception_code='set-operation-misuse',
        concept_terms=['set', 'unique', 'member'], action_terms=['set', 'sort', 'unique', 'return'],
        strategy='Convert the numbers to a set to remove duplicates, then return the sorted values as a new list.',
        transfer={'title': 'Common-number Transfer Check', 'prompt': 'Return an ascending list of values that occur in both input lists, with no duplicates.', 'test_ids': ['common-numbers-public', 'common-numbers-empty', 'common-numbers-other'], 'action_terms': ['set', 'intersection', 'unique', 'sort']},
        recommendation='Review set uniqueness and set intersections, then retry a set exercise.',
    ),
    _expansion_entry(
        slug='set-membership-count', order=30, title='Count values found in an allowed set',
        prompt='Return how many values in numbers also occur in allowed_values.',
        starter_code='def count_allowed(numbers, allowed_values):\n    return 0',
        public_description='count_allowed([1, 2, 4, 2], [2, 3]) should return 2.',
        public_test_ids=['set-membership-public'], hidden_test_ids=['set-membership-none', 'set-membership-other'],
        concept='set_operations', misconception_code='set-operation-misuse',
        concept_terms=['set', 'unique', 'member'], action_terms=['set', 'member', 'count', 'return'],
        strategy='Create a set of allowed values and count each input number whose membership test is true.',
        transfer={'title': 'Missing-number Transfer Check', 'prompt': 'Return an ascending list of values in expected_values that do not occur in actual_values.', 'test_ids': ['missing-numbers-public', 'missing-numbers-empty', 'missing-numbers-other'], 'action_terms': ['set', 'member', 'difference', 'sort']},
        recommendation='Review set membership checks and value counting, then retry a set exercise.',
    ),
    _expansion_entry(
        slug='even-squares-comprehension', order=31, title='Build even squares with a comprehension',
        prompt='Return squares of only the even numbers in numbers, preserving their input order.',
        starter_code='def even_squares(numbers):\n    return []',
        public_description='even_squares([1, 2, 3, 4]) should return [4, 16].',
        public_test_ids=['even-squares-public'], hidden_test_ids=['even-squares-empty', 'even-squares-negative'],
        concept='list_comprehensions', misconception_code='comprehension-misuse',
        concept_terms=['comprehension', 'list', 'expression'], action_terms=['filter', 'square', 'list', 'return'],
        strategy='Use a list comprehension that filters numbers with number % 2 == 0 and produces number * number.',
        transfer={'title': 'Uppercase-word Transfer Check', 'prompt': 'Return uppercase versions of words whose length is at least four.', 'test_ids': ['uppercase-words-public', 'uppercase-words-empty', 'uppercase-words-other'], 'action_terms': ['comprehension', 'filter', 'uppercase', 'list']},
        recommendation='Review list-comprehension filtering and expressions, then retry a comprehension exercise.',
    ),
    _expansion_entry(
        slug='word-lengths-comprehension', order=32, title='Build word lengths with a comprehension',
        prompt='Return a list containing the length of each word in words.',
        starter_code='def word_lengths(words):\n    return []',
        public_description='word_lengths(["hi", "python"]) should return [2, 6].',
        public_test_ids=['word-lengths-public'], hidden_test_ids=['word-lengths-empty', 'word-lengths-other'],
        concept='list_comprehensions', misconception_code='comprehension-misuse',
        concept_terms=['comprehension', 'list', 'expression'], action_terms=['length', 'transform', 'list', 'return'],
        strategy='Use a list comprehension that applies len to every current word and collects the resulting lengths.',
        transfer={'title': 'Positive-number Transfer Check', 'prompt': 'Return a list containing only positive numbers from numbers.', 'test_ids': ['positive-numbers-public', 'positive-numbers-empty', 'positive-numbers-other'], 'action_terms': ['comprehension', 'filter', 'positive', 'list']},
        recommendation='Review comprehension transformations and output lists, then retry a comprehension exercise.',
    ),
    _expansion_entry(
        slug='safe-to-int', order=33, title='Convert text to an integer safely',
        prompt='Return the integer represented by text, or None when text cannot be converted.',
        starter_code='def safe_to_int(text):\n    return None',
        public_description='safe_to_int("42") should return 42.',
        public_test_ids=['safe-int-public'], hidden_test_ids=['safe-int-invalid', 'safe-int-negative'],
        concept='exception_handling', misconception_code='exception-handling-misuse',
        concept_terms=['try', 'except', 'error'], action_terms=['convert', 'except', 'return', 'integer'],
        strategy='Try to return int(text), and catch ValueError to return None for invalid text.',
        transfer={'title': 'Safe-list-index Transfer Check', 'prompt': 'Return items[index], or None when index is outside the list.', 'test_ids': ['safe-index-public', 'safe-index-negative', 'safe-index-outside'], 'action_terms': ['try', 'except', 'index', 'return']},
        recommendation='Review focused try-except blocks for expected invalid input, then retry an exception exercise.',
    ),
    _expansion_entry(
        slug='safe-dictionary-number', order=34, title='Read a dictionary number safely',
        prompt='Return the integer value stored at key, or None when the key is missing or its value cannot be converted to an integer.',
        starter_code='def safe_dictionary_number(values, key):\n    return None',
        public_description='safe_dictionary_number({"age": "12"}, "age") should return 12.',
        public_test_ids=['safe-dict-number-public'], hidden_test_ids=['safe-dict-number-missing', 'safe-dict-number-invalid'],
        concept='exception_handling', misconception_code='exception-handling-misuse',
        concept_terms=['try', 'except', 'error'], action_terms=['key', 'convert', 'except', 'return'],
        strategy='Try to read values[key] and convert it with int, returning None when KeyError or ValueError occurs.',
        transfer={'title': 'Safe-reciprocal Transfer Check', 'prompt': 'Return 1 divided by number, or None when conversion fails or the number is zero.', 'test_ids': ['safe-reciprocal-public', 'safe-reciprocal-zero', 'safe-reciprocal-invalid'], 'action_terms': ['try', 'except', 'zero', 'return']},
        recommendation='Review handling only the expected conversion and lookup errors, then retry an exception exercise.',
    ),
    _expansion_entry(
        slug='is-prime-number', order=35, title='Check whether a number is prime',
        prompt='Return True when n is a prime number and False otherwise.',
        starter_code='def is_prime(n):\n    return False',
        public_description='is_prime(29) should return True.',
        public_test_ids=['prime-public'], hidden_test_ids=['prime-one', 'prime-composite'],
        concept='numeric_algorithms', misconception_code='numeric-algorithm-misuse',
        concept_terms=['number', 'remainder', 'divisor'], action_terms=['divisor', 'remainder', 'loop', 'return'],
        strategy='Reject numbers below two, then test possible divisors and return False when n has remainder zero for any divisor.',
        transfer={'title': 'Greatest-common-divisor Transfer Check', 'prompt': 'Return the greatest common divisor of two non-negative integers.', 'test_ids': ['gcd-public', 'gcd-zero', 'gcd-other'], 'action_terms': ['remainder', 'divisor', 'loop', 'return']},
        recommendation='Review divisors, remainders, and numeric boundary cases, then retry a numeric exercise.',
    ),
    _expansion_entry(
        slug='digit-sum', order=36, title='Sum the digits of a number',
        prompt='Return the sum of decimal digits in non-negative integer n.',
        starter_code='def digit_sum(n):\n    return 0',
        public_description='digit_sum(482) should return 14.',
        public_test_ids=['digit-sum-public'], hidden_test_ids=['digit-sum-zero', 'digit-sum-other'],
        concept='numeric_algorithms', misconception_code='numeric-algorithm-misuse',
        concept_terms=['number', 'remainder', 'divisor'], action_terms=['remainder', 'divide', 'sum', 'return'],
        strategy='Repeatedly add n % 10 to a total and replace n with n // 10 until no digits remain.',
        transfer={'title': 'Digit-count Transfer Check', 'prompt': 'Return the number of decimal digits in non-negative integer n, treating zero as one digit.', 'test_ids': ['digit-count-public', 'digit-count-zero', 'digit-count-other'], 'action_terms': ['remainder', 'divide', 'count', 'return']},
        recommendation='Review integer division, remainders, and numeric boundary cases, then retry a numeric exercise.',
    ),
    _expansion_entry(
        slug='two-pointer-pair-sum', order=37, title='Find a pair sum with two pointers',
        prompt='Return True when sorted numbers contains two distinct values whose sum is target.',
        starter_code='def has_pair_sum(numbers, target):\n    return False',
        public_description='has_pair_sum([1, 2, 4, 7], 9) should return True.',
        public_test_ids=['pair-sum-public'], hidden_test_ids=['pair-sum-missing', 'pair-sum-duplicate'],
        concept='two_pointers', misconception_code='two-pointer-misuse',
        concept_terms=['pointer', 'left', 'right'], action_terms=['left', 'right', 'sum', 'move'],
        strategy='Start left and right at opposite ends; compare their sum with target and move the pointer that makes the sum closer.',
        transfer={'title': 'Palindrome-pointer Transfer Check', 'prompt': 'Return True when text is a palindrome by comparing characters from its left and right ends.', 'test_ids': ['pointer-palindrome-public', 'pointer-palindrome-false', 'pointer-palindrome-empty'], 'action_terms': ['left', 'right', 'compare', 'move']},
        recommendation='Review the sorted-data two-pointer invariant and pointer moves, then retry a two-pointer exercise.',
    ),
    _expansion_entry(
        slug='remove-duplicates-two-pointers', order=38, title='Remove sorted duplicates with two pointers',
        prompt='Return a new list containing each value from sorted numbers once, preserving ascending order.',
        starter_code='def remove_sorted_duplicates(numbers):\n    return []',
        public_description='remove_sorted_duplicates([1, 1, 2, 2, 3]) should return [1, 2, 3].',
        public_test_ids=['remove-duplicates-public'], hidden_test_ids=['remove-duplicates-empty', 'remove-duplicates-other'],
        concept='two_pointers', misconception_code='two-pointer-misuse',
        concept_terms=['pointer', 'left', 'right'], action_terms=['pointer', 'compare', 'append', 'move'],
        strategy='Keep one pointer or result position for the last unique value and scan forward, appending only values different from the previous one.',
        transfer={'title': 'Sorted-square Transfer Check', 'prompt': 'Return squares of sorted numbers in ascending order using two pointers.', 'test_ids': ['sorted-squares-public', 'sorted-squares-empty', 'sorted-squares-other'], 'action_terms': ['left', 'right', 'square', 'move']},
        recommendation='Review comparing ordered values and moving pointers without losing order, then retry a two-pointer exercise.',
    ),
    _expansion_entry(
        slug='maximum-window-sum', order=39, title='Find a maximum fixed-window sum',
        prompt='Return the largest sum of any contiguous window of size k in numbers; return 0 when k is zero or larger than the list.',
        starter_code='def maximum_window_sum(numbers, k):\n    return 0',
        public_description='maximum_window_sum([2, 1, 5, 1, 3, 2], 3) should return 9.',
        public_test_ids=['window-sum-public'], hidden_test_ids=['window-sum-zero', 'window-sum-other'],
        concept='sliding_window', misconception_code='sliding-window-misuse',
        concept_terms=['window', 'left', 'right'], action_terms=['window', 'sum', 'remove', 'add'],
        strategy='Keep a running sum, add the entering value, remove the value leaving once the window exceeds k, and track the largest valid sum.',
        transfer={'title': 'Window-average Transfer Check', 'prompt': 'Return the largest average of any contiguous window of size k, or 0 when no valid window exists.', 'test_ids': ['window-average-public', 'window-average-zero', 'window-average-other'], 'action_terms': ['window', 'sum', 'remove', 'add']},
        recommendation='Review the running window sum and both window boundaries, then retry a sliding-window exercise.',
    ),
    _expansion_entry(
        slug='longest-unique-substring', order=40, title='Find the longest unique-character substring',
        prompt='Return the length of the longest substring of text with no repeated character.',
        starter_code='def longest_unique_length(text):\n    return 0',
        public_description='longest_unique_length("abcabcbb") should return 3.',
        public_test_ids=['longest-unique-public'], hidden_test_ids=['longest-unique-empty', 'longest-unique-other'],
        concept='sliding_window', misconception_code='sliding-window-misuse',
        concept_terms=['window', 'left', 'right'], action_terms=['window', 'character', 'left', 'length'],
        strategy='Track each character position, move the left boundary past a repeated character, and update the largest current window length.',
        transfer={'title': 'At-most-two-distinct Transfer Check', 'prompt': 'Return the longest substring length containing at most two distinct characters.', 'test_ids': ['two-distinct-public', 'two-distinct-empty', 'two-distinct-other'], 'action_terms': ['window', 'left', 'character', 'count']},
        recommendation='Review moving the left boundary and maintaining window state, then retry a sliding-window exercise.',
    ),
    _expansion_entry(
        slug='minimum-coin-count', order=41, title='Choose coins greedily',
        prompt='Return the minimum number of coins needed for amount using coin values 25, 10, 5, and 1.',
        starter_code='def minimum_coin_count(amount):\n    return 0',
        public_description='minimum_coin_count(41) should return 4.',
        public_test_ids=['coin-count-public'], hidden_test_ids=['coin-count-zero', 'coin-count-other'],
        concept='greedy_algorithms', misconception_code='greedy-choice-misuse',
        concept_terms=['greedy', 'choice', 'smallest'], action_terms=['largest', 'coin', 'remainder', 'count'],
        strategy='For each coin value from largest to smallest, take as many coins as possible and keep the remaining amount.',
        transfer={'title': 'Change-breakdown Transfer Check', 'prompt': 'Return a list of coin values used to make amount with coins 25, 10, 5, and 1, from largest to smallest.', 'test_ids': ['change-breakdown-public', 'change-breakdown-zero', 'change-breakdown-other'], 'action_terms': ['greedy', 'largest', 'coin', 'remainder']},
        recommendation='Review greedy largest-first choices and remaining amounts, then retry a greedy exercise.',
    ),
    _expansion_entry(
        slug='maximum-activities', order=42, title='Schedule the maximum activities',
        prompt='Return the maximum number of non-overlapping activities from intervals [start, end], where an activity may start when another ends.',
        starter_code='def maximum_activities(intervals):\n    return 0',
        public_description='maximum_activities([[1, 3], [2, 4], [3, 5], [5, 6]]) should return 3.',
        public_test_ids=['activities-public'], hidden_test_ids=['activities-empty', 'activities-other'],
        concept='greedy_algorithms', misconception_code='greedy-choice-misuse',
        concept_terms=['greedy', 'choice', 'smallest'], action_terms=['sort', 'end', 'choose', 'count'],
        strategy='Sort activities by end time and choose the next activity only when its start is at least the end of the last chosen activity.',
        transfer={'title': 'Non-overlapping-interval Transfer Check', 'prompt': 'Return an end-time-sorted list of chosen non-overlapping intervals using the earliest-finish greedy rule.', 'test_ids': ['chosen-intervals-public', 'chosen-intervals-empty', 'chosen-intervals-other'], 'action_terms': ['sort', 'end', 'choose', 'greedy']},
        recommendation='Review earliest-finish greedy choices and the non-overlap condition, then retry a greedy exercise.',
    ),
    _expansion_entry(
        slug='generate-subsets', order=43, title='Generate all subsets with backtracking',
        prompt='Return every subset of distinct numbers as a list of lists, sorted by subset length and then lexicographically.',
        starter_code='def generate_subsets(numbers):\n    return [[]]',
        public_description='generate_subsets([1, 2]) should return [[], [1], [2], [1, 2]].',
        public_test_ids=['subsets-public'], hidden_test_ids=['subsets-empty', 'subsets-other'],
        concept='backtracking', misconception_code='backtracking-misuse',
        concept_terms=['backtracking', 'choice', 'recursive'], action_terms=['choose', 'append', 'remove', 'recursive'],
        strategy='Recursively choose whether to include each number, append a copy at the base case, then undo the choice before exploring the other branch.',
        transfer={'title': 'Binary-string Transfer Check', 'prompt': 'Return all binary strings of length n in lexicographic order using backtracking.', 'test_ids': ['binary-strings-public', 'binary-strings-zero', 'binary-strings-other'], 'action_terms': ['backtracking', 'choice', 'append', 'recursive']},
        recommendation='Review recursive choices, copying results, and undoing a choice before the next branch, then retry a backtracking exercise.',
    ),
    _expansion_entry(
        slug='generate-parentheses', order=44, title='Generate balanced parentheses',
        prompt='Return all balanced strings containing n pairs of parentheses in lexicographic order.',
        starter_code='def generate_parentheses(n):\n    return []',
        public_description='generate_parentheses(2) should return ["(())", "()()"].',
        public_test_ids=['parentheses-public'], hidden_test_ids=['parentheses-zero', 'parentheses-other'],
        concept='backtracking', misconception_code='backtracking-misuse',
        concept_terms=['backtracking', 'choice', 'recursive'], action_terms=['open', 'close', 'append', 'recursive'],
        strategy='Backtrack by adding an opening parenthesis while openings remain and a closing parenthesis only when it cannot exceed openings.',
        transfer={'title': 'Letter-combination Transfer Check', 'prompt': 'Return all strings formed by choosing one character from each string in choices, in lexicographic order.', 'test_ids': ['letter-combinations-public', 'letter-combinations-empty', 'letter-combinations-other'], 'action_terms': ['backtracking', 'choice', 'append', 'recursive']},
        recommendation='Review valid recursive choices and backtracking after each partial string, then retry a backtracking exercise.',
    ),
)

CODING_CATALOG += EXPANDED_PRACTICE_CATALOG


# Concrete drill contracts for the high-volume practice series.  A drill keeps
# the target concept constant while its level supplies different normal and
# boundary data through the isolated runner.
_BULK_TASKS = {
    'conditional': ('Return "negative", "zero", or "positive" for number.', 'def solve(number):\n    return ""', 'solve(-3) should return "negative".', 'Use ordered if-elif-else branches for the three number cases.'),
    'function': ('Return the product of a and b.', 'def solve(a, b):\n    return 0', 'solve(3, 4) should return 12.', 'Use both parameters and return their product.'),
    'list': ('Return the sum of all numbers in values.', 'def solve(values):\n    return 0', 'solve([2, 3, 4]) should return 9.', 'Visit each list value and maintain a running total.'),
    'string': ('Return text with its characters reversed.', 'def solve(text):\n    return ""', 'solve("code") should return "edoc".', 'Use string character order to return the reverse.'),
    'loop': ('Return a new list with one added to every number.', 'def solve(numbers):\n    return []', 'solve([1, 3]) should return [2, 4].', 'Loop over each current number and append its adjusted value.'),
    'recursion': ('Return 1 + 2 + ... + n recursively for non-negative n.', 'def solve(n):\n    return 0', 'solve(4) should return 10.', 'Use a zero base case and a recursive call with n - 1.'),
    'dictionary': ('Return the value for key in values, or None if it is missing.', 'def solve(values, key):\n    return None', 'solve({"a": 1}, "a") should return 1.', 'Treat the supplied key as a dictionary key and use a safe fallback.'),
    'search': ('Return the index of target in sorted values, or -1 if absent.', 'def solve(values, target):\n    return -1', 'solve([1, 3, 5], 3) should return 1.', 'Use binary-search boundaries and compare the middle value.'),
    'stack': ('Return True when parentheses in text are balanced.', 'def solve(text):\n    return True', 'solve("(())") should return True.', 'Push opening parentheses and pop for closing parentheses.'),
    'sorting': ('Return a new ascending list from values.', 'def solve(values):\n    return []', 'solve([3, 1, 2]) should return [1, 2, 3].', 'Preserve a sorted-result invariant while ordering the values.'),
    'hash': ('Return the first repeated value in values, or None.', 'def solve(values):\n    return None', 'solve([2, 1, 2]) should return 2.', 'Track seen values with a hash-based structure.'),
    'graph': ('Return the number of nodes reachable from start in graph.', 'def solve(graph, start):\n    return 0', 'solve({"A": ["B"], "B": []}, "A") should return 2.', 'Traverse graph neighbors while recording visited nodes.'),
    'dp': ('Return the nth Fibonacci number with F(0)=0 and F(1)=1.', 'def solve(n):\n    return 0', 'solve(6) should return 8.', 'Build the answer from the two previous dynamic-programming states.'),
    'set': ('Return an ascending list of unique values from values.', 'def solve(values):\n    return []', 'solve([2, 1, 2]) should return [1, 2].', 'Use a set to remove duplicate values before sorting.'),
    'comprehension': ('Return squares of the even values in numbers.', 'def solve(numbers):\n    return []', 'solve([1, 2, 3, 4]) should return [4, 16].', 'Use a list comprehension with a filter and an expression.'),
    'exception': ('Return int(text), or None when conversion fails.', 'def solve(text):\n    return None', 'solve("42") should return 42.', 'Use try-except to handle invalid integer conversion.'),
    'numeric': ('Return the sum of decimal digits in non-negative n.', 'def solve(n):\n    return 0', 'solve(482) should return 14.', 'Use remainders and integer division to process each digit.'),
    'two-pointer': ('Return True when sorted values contains a pair totaling target.', 'def solve(values, target):\n    return False', 'solve([1, 2, 4, 7], 9) should return True.', 'Move left and right pointers according to their current sum.'),
    'window': ('Return the largest sum of a contiguous window of size k.', 'def solve(values, k):\n    return 0', 'solve([2, 1, 5, 1], 2) should return 6.', 'Maintain a running sum as a fixed-size window slides.'),
    'greedy': ('Return the number of US coins needed for amount using 25, 10, 5, and 1.', 'def solve(amount):\n    return 0', 'solve(41) should return 4.', 'Choose as many of the largest available coins as possible.'),
    'backtracking': ('Return all binary strings of length n in lexicographic order.', 'def solve(n):\n    return []', 'solve(2) should return ["00", "01", "10", "11"].', 'Recursively choose a character, then undo that choice before the next branch.'),
}


def _bulk_practice_entries():
    entries = []
    order = 45
    for _topic_slug, topic_name, concept, misconception_code, existing_count, mode in BULK_SERIES:
        prompt, starter_code, public_description, strategy = _BULK_TASKS[mode]
        concept_terms = concept.replace('_', ' ').split()
        for level_number in range(existing_count + 1, 11):
            level = PRACTICE_LEVELS[(level_number - existing_count - 1) % len(PRACTICE_LEVELS)]
            slug = f'{_topic_slug}-practice-{level_number}'
            entries.append(_expansion_entry(
                slug=slug, order=order, title=f'{topic_name}: {level.title()} {level_number}',
                prompt=prompt, starter_code=starter_code,
                public_description=public_description,
                public_test_ids=[f'{slug}-public'],
                hidden_test_ids=[f'{slug}-boundary', f'{slug}-mixed'],
                concept=concept, misconception_code=misconception_code,
                concept_terms=concept_terms, action_terms=['solve', 'return', 'result'],
                strategy=strategy,
                transfer={
                    'title': f'{topic_name}: parallel {level.title()} Transfer Check',
                    'prompt': f'Write transfer_solve for a parallel {topic_name.lower()} case using the same core rule.',
                    'test_ids': [f'{slug}-transfer-public', f'{slug}-transfer-boundary', f'{slug}-transfer-mixed'],
                    'action_terms': ['transfer_solve', 'rule', 'return'],
                },
                recommendation=f'Review the {topic_name.lower()} rule, then retry a parallel practice drill.',
            ))
            order += 1
    return tuple(entries)


CODING_CATALOG += _bulk_practice_entries()
