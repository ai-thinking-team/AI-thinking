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


def _entry(*, slug, order, title, prompt, starter_code, public_description,
           public_test_ids, hidden_test_ids, operation, operation_terms,
           diagnosis_question, diagnosis_hints, diagnosis_answer, revision_hints,
           revision_solution, teach_back_answer, transfer, active=True):
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
        'rubric': {
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
)
