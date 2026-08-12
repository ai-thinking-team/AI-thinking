from collections import Counter
import re

from runner_service.harness import TEST_CATALOG


REQUIRED_ENTRY_KEYS = {
    'slug', 'display_order', 'title', 'prompt', 'starter_code',
    'public_test_description', 'public_test_ids', 'hidden_test_ids',
    'operation', 'rubric', 'transfer', 'active',
}

STABLE_CODE_PATTERN = re.compile(r'[a-z0-9][a-z0-9_-]{0,79}')


def _non_empty_string_errors(value, *, field):
    if not isinstance(value, str) or not value.strip():
        return [f'{field} must be a non-empty string.']
    return []


def _string_list_errors(value, *, field, exact_length=None):
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        return [f'{field} must be a non-empty list of strings.']
    if exact_length is not None and len(value) != exact_length:
        return [f'{field} must contain exactly {exact_length} items.']
    duplicates = sorted(item for item, count in Counter(value).items() if count > 1)
    if duplicates:
        return [f'{field} contains duplicate values: {", ".join(duplicates)}.']
    return []


def _focused_question_errors(value, *, field):
    errors = _non_empty_string_errors(value, field=field)
    if errors:
        return errors
    if value.count('?') != 1 or not value.strip().endswith('?'):
        return [f'{field} must contain exactly one focused question.']
    return []


def _teach_back_errors(teach_back, *, field, allowed_codes):
    if not isinstance(teach_back, dict):
        return [f'{field} must be an object.']
    errors = []
    criteria = teach_back.get('criteria')
    if not isinstance(criteria, list) or not criteria:
        return [f'{field}.criteria must contain at least one criterion.']

    criterion_ids = []
    criterion_fields = []
    for index, criterion in enumerate(criteria):
        criterion_field = f'{field}.criteria[{index}]'
        if not isinstance(criterion, dict):
            errors.append(f'{criterion_field} must be an object.')
            continue
        for key in ('id', 'field', 'feedback'):
            errors.extend(_non_empty_string_errors(
                criterion.get(key),
                field=f'{criterion_field}.{key}',
            ))
        errors.extend(_focused_question_errors(
            criterion.get('follow_up_question'),
            field=f'{criterion_field}.follow_up_question',
        ))
        required_for_clear = criterion.get('required_for_clear', True)
        if not isinstance(required_for_clear, bool):
            errors.append(f'{criterion_field}.required_for_clear must be a boolean.')
        groups = criterion.get('required_groups')
        if not isinstance(groups, list) or not groups:
            errors.append(f'{criterion_field}.required_groups must contain marker groups.')
        else:
            for group_index, group in enumerate(groups):
                errors.extend(_string_list_errors(
                    group,
                    field=f'{criterion_field}.required_groups[{group_index}]',
                ))
        if isinstance(criterion.get('id'), str) and criterion['id'].strip():
            criterion_ids.append(criterion['id'])
        if isinstance(criterion.get('field'), str) and criterion['field'].strip():
            criterion_fields.append(criterion['field'])

    for name, values in (('id', criterion_ids), ('field', criterion_fields)):
        duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
        if duplicates:
            errors.append(
                f'{field}.criteria contains duplicate {name} values: {", ".join(duplicates)}.'
            )

    misconceptions = teach_back.get('misconceptions', [])
    if not isinstance(misconceptions, list):
        errors.append(f'{field}.misconceptions must be a list.')
        return errors
    misconception_codes = []
    for index, misconception in enumerate(misconceptions):
        misconception_field = f'{field}.misconceptions[{index}]'
        if not isinstance(misconception, dict):
            errors.append(f'{misconception_field} must be an object.')
            continue
        code = misconception.get('code')
        errors.extend(_non_empty_string_errors(code, field=f'{misconception_field}.code'))
        if isinstance(code, str) and code.strip():
            misconception_codes.append(code)
            if not STABLE_CODE_PATTERN.fullmatch(code):
                errors.append(f'{misconception_field}.code must be a stable slug code.')
            elif code not in allowed_codes:
                errors.append(
                    f'{misconception_field}.code must appear in allowed_misconception_codes.'
                )
        errors.extend(_string_list_errors(
            misconception.get('fields'),
            field=f'{misconception_field}.fields',
        ))
        fields = misconception.get('fields')
        if isinstance(fields, list) and all(isinstance(item, str) for item in fields):
            unknown_fields = sorted(set(fields) - set(criterion_fields))
            if unknown_fields:
                errors.append(
                    f'{misconception_field}.fields contains unknown rubric fields: '
                    f'{", ".join(unknown_fields)}.'
                )
        errors.extend(_string_list_errors(
            misconception.get('indicators'),
            field=f'{misconception_field}.indicators',
        ))
        errors.extend(_non_empty_string_errors(
            misconception.get('feedback'),
            field=f'{misconception_field}.feedback',
        ))
        errors.extend(_focused_question_errors(
            misconception.get('follow_up_question'),
            field=f'{misconception_field}.follow_up_question',
        ))
    duplicates = sorted(
        code for code, count in Counter(misconception_codes).items() if count > 1
    )
    if duplicates:
        errors.append(
            f'{field}.misconceptions contains duplicate codes: {", ".join(duplicates)}.'
        )
    return errors


def _test_id_errors(ids, *, field, test_catalog):
    errors = []
    if not isinstance(ids, list) or not ids or any(not isinstance(item, str) or not item for item in ids):
        return [f'{field} must be a non-empty list of test ID strings.']
    unknown = sorted(set(ids) - set(test_catalog))
    if unknown:
        errors.append(f'{field} contains unknown runner test IDs: {", ".join(unknown)}.')
    duplicates = sorted(item for item, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append(f'{field} contains duplicate test IDs: {", ".join(duplicates)}.')
    return errors


def _validate_entry(item, *, index, test_catalog):
    prefix = f'catalog[{index}]'
    errors = []
    if not isinstance(item, dict):
        return [f'{prefix} must be an object.']
    missing = sorted(REQUIRED_ENTRY_KEYS - set(item))
    errors.extend(f'{prefix} is missing {key}.' for key in missing)
    if missing:
        return errors
    if not isinstance(item['slug'], str) or not item['slug'].strip():
        errors.append(f'{prefix}.slug must be a non-empty string.')
    if (
        isinstance(item['display_order'], bool)
        or not isinstance(item['display_order'], int)
        or item['display_order'] < 0
    ):
        errors.append(f'{prefix}.display_order must be a non-negative integer.')
    for key in ('title', 'prompt', 'starter_code', 'public_test_description', 'operation'):
        if not isinstance(item[key], str) or not item[key].strip():
            errors.append(f'{prefix}.{key} must be a non-empty string.')
    if not isinstance(item['active'], bool):
        errors.append(f'{prefix}.active must be a boolean.')

    public_ids = item['public_test_ids']
    hidden_ids = item['hidden_test_ids']
    errors.extend(_test_id_errors(public_ids, field=f'{prefix}.public_test_ids', test_catalog=test_catalog))
    errors.extend(_test_id_errors(hidden_ids, field=f'{prefix}.hidden_test_ids', test_catalog=test_catalog))
    public_ids_are_strings = isinstance(public_ids, list) and all(
        isinstance(test_id, str) for test_id in public_ids
    )
    hidden_ids_are_strings = isinstance(hidden_ids, list) and all(
        isinstance(test_id, str) for test_id in hidden_ids
    )
    if public_ids_are_strings:
        not_public = sorted(test_id for test_id in public_ids if test_id in test_catalog and not test_catalog[test_id].get('public'))
        errors.extend(f'{prefix}.public_test_ids must use public runner cases: {", ".join(not_public)}.' for _ in [0] if not_public)
    if hidden_ids_are_strings:
        accidentally_public = sorted(test_id for test_id in hidden_ids if test_id in test_catalog and test_catalog[test_id].get('public'))
        if accidentally_public:
            errors.append(f'{prefix}.hidden_test_ids cannot use public runner cases: {", ".join(accidentally_public)}.')
    if public_ids_are_strings and hidden_ids_are_strings:
        overlap = sorted(set(public_ids) & set(hidden_ids))
        if overlap:
            errors.append(f'{prefix} reuses test IDs in public and hidden lists: {", ".join(overlap)}.')

    rubric = item['rubric']
    if not isinstance(rubric, dict):
        errors.append(f'{prefix}.rubric must be an object.')
    else:
        for key in (
            'concept', 'operation', 'allowed_misconception_codes',
            'diagnosis_action_terms', 'diagnosis', 'revision_hints',
            'revision_solution', 'teach_back', 'teach_back_followups',
            'teach_back_answer',
        ):
            if key not in rubric:
                errors.append(f'{prefix}.rubric is missing {key}.')
        for key in ('concept', 'operation', 'revision_solution', 'teach_back_answer'):
            errors.extend(_non_empty_string_errors(
                rubric.get(key),
                field=f'{prefix}.rubric.{key}',
            ))
        allowed_codes = rubric.get('allowed_misconception_codes')
        errors.extend(_string_list_errors(
            allowed_codes,
            field=f'{prefix}.rubric.allowed_misconception_codes',
        ))
        if isinstance(allowed_codes, list) and all(isinstance(code, str) for code in allowed_codes):
            for code in allowed_codes:
                if code and not STABLE_CODE_PATTERN.fullmatch(code):
                    errors.append(
                        f'{prefix}.rubric.allowed_misconception_codes contains an invalid code: {code}.'
                    )
        errors.extend(_string_list_errors(
            rubric.get('diagnosis_action_terms'),
            field=f'{prefix}.rubric.diagnosis_action_terms',
        ))
        diagnosis = rubric.get('diagnosis')
        if not isinstance(diagnosis, dict):
            errors.append(f'{prefix}.rubric.diagnosis must be an object.')
        else:
            for key in ('question', 'hints', 'answer'):
                if key not in diagnosis:
                    errors.append(f'{prefix}.rubric.diagnosis is missing {key}.')
            errors.extend(_focused_question_errors(
                diagnosis.get('question'),
                field=f'{prefix}.rubric.diagnosis.question',
            ))
            errors.extend(_non_empty_string_errors(
                diagnosis.get('answer'),
                field=f'{prefix}.rubric.diagnosis.answer',
            ))
            diagnosis_hints = diagnosis.get('hints')
            if not isinstance(diagnosis_hints, dict):
                errors.append(f'{prefix}.rubric.diagnosis.hints must be an object.')
            else:
                for level in ('2', '3', '4'):
                    errors.extend(_focused_question_errors(
                        diagnosis_hints.get(level),
                        field=f'{prefix}.rubric.diagnosis.hints.{level}',
                    ))
        revision_hints = rubric.get('revision_hints')
        errors.extend(_string_list_errors(
            revision_hints,
            field=f'{prefix}.rubric.revision_hints',
            exact_length=4,
        ))
        if isinstance(revision_hints, list):
            for index, hint in enumerate(revision_hints):
                errors.extend(_focused_question_errors(
                    hint,
                    field=f'{prefix}.rubric.revision_hints[{index}]',
                ))
        teach_back = rubric.get('teach_back')
        errors.extend(_teach_back_errors(
            teach_back,
            field=f'{prefix}.rubric.teach_back',
            allowed_codes=(
                set(allowed_codes)
                if isinstance(allowed_codes, list)
                and all(isinstance(code, str) for code in allowed_codes)
                else set()
            ),
        ))
        teach_back_followups = rubric.get('teach_back_followups')
        if not isinstance(teach_back_followups, dict):
            errors.append(f'{prefix}.rubric.teach_back_followups must be an object.')
        else:
            for level in ('2', '3', '4'):
                errors.extend(_focused_question_errors(
                    teach_back_followups.get(level),
                    field=f'{prefix}.rubric.teach_back_followups.{level}',
                ))

    transfer = item['transfer']
    if not isinstance(transfer, dict):
        errors.append(f'{prefix}.transfer must be an object.')
    else:
        for key in ('title', 'prompt', 'test_ids', 'action_terms'):
            if key not in transfer:
                errors.append(f'{prefix}.transfer is missing {key}.')
        errors.extend(_non_empty_string_errors(
            transfer.get('title'),
            field=f'{prefix}.transfer.title',
        ))
        errors.extend(_non_empty_string_errors(
            transfer.get('prompt'),
            field=f'{prefix}.transfer.prompt',
        ))
        transfer_ids = transfer.get('test_ids')
        errors.extend(_test_id_errors(transfer_ids, field=f'{prefix}.transfer.test_ids', test_catalog=test_catalog))
        if isinstance(transfer_ids, list) and all(
            isinstance(test_id, str) for test_id in transfer_ids
        ):
            public_transfer = sorted(test_id for test_id in transfer_ids if test_id in test_catalog and test_catalog[test_id].get('public'))
            if public_transfer:
                errors.append(f'{prefix}.transfer.test_ids must use hidden runner cases: {", ".join(public_transfer)}.')
        errors.extend(_string_list_errors(
            transfer.get('action_terms'),
            field=f'{prefix}.transfer.action_terms',
        ))
    return errors


def validate_catalog(catalog, *, test_catalog=TEST_CATALOG):
    if not isinstance(catalog, (list, tuple)) or not catalog:
        return ['Catalog must be a non-empty list or tuple.']
    errors = []
    slugs = []
    orders = []
    titles = []
    for index, item in enumerate(catalog):
        errors.extend(_validate_entry(item, index=index, test_catalog=test_catalog))
        if isinstance(item, dict):
            if isinstance(item.get('slug'), str):
                slugs.append(item['slug'])
            if isinstance(item.get('display_order'), int) and not isinstance(
                item.get('display_order'), bool
            ):
                orders.append(item['display_order'])
            if isinstance(item.get('title'), str):
                titles.append(item['title'])
    for field, values in (('slug', slugs), ('display_order', orders), ('title', titles)):
        duplicates = sorted(value for value, count in Counter(values).items() if value is not None and count > 1)
        if duplicates:
            errors.append(f'Catalog contains duplicate {field} values: {", ".join(map(str, duplicates))}.')
    return errors


def database_exercise_payload(exercise):
    transfer = exercise.transfer_activity
    activity_rubric = exercise.activity.rubric
    transfer_rubric = transfer.rubric if transfer and isinstance(transfer.rubric, dict) else {}
    return {
        'slug': exercise.slug,
        'display_order': exercise.display_order,
        'active': exercise.active,
        'title': exercise.activity.title,
        'prompt': exercise.activity.prompt,
        'starter_code': exercise.starter_code,
        'public_test_description': exercise.public_test_description,
        'public_test_ids': exercise.public_test_ids,
        'hidden_test_ids': exercise.hidden_test_ids,
        'operation': activity_rubric.get('operation', '') if isinstance(activity_rubric, dict) else '',
        'rubric': activity_rubric,
        'transfer': {
            'title': transfer.title if transfer else '',
            'prompt': transfer.prompt if transfer else '',
            'test_ids': exercise.transfer_test_ids,
            'action_terms': transfer_rubric.get('action_terms', []),
        },
    }


def validate_database_exercise(exercise):
    return _validate_entry(database_exercise_payload(exercise), index=exercise.pk or 'new', test_catalog=TEST_CATALOG)
