import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from .bulk_practice import BULK_SERIES
except ImportError:  # The Docker image executes this module as a script.
    from bulk_practice import BULK_SERIES

TEST_CATALOG = {
    'divide-public': {'function': 'safe_divide', 'args': (6, 3), 'expected': 2.0, 'public': True},
    'divide-by-zero': {'function': 'safe_divide', 'args': (9, 0), 'expected': 0, 'public': False},
    'divide-negative': {'function': 'safe_divide', 'args': (-8, 2), 'expected': -4.0, 'public': False},
    'percentage-public': {'function': 'safe_percentage', 'args': (1, 4), 'expected': 25.0, 'public': False},
    'percentage-zero': {'function': 'safe_percentage', 'args': (5, 0), 'expected': 0, 'public': False},
    'percentage-other': {'function': 'safe_percentage', 'args': (3, 5), 'expected': 60.0, 'public': False},
    'first-item-public': {'function': 'first_item', 'args': ([4, 8],), 'expected': 4, 'public': True},
    'first-item-empty': {'function': 'first_item', 'args': ([],), 'expected': None, 'public': False},
    'first-item-single': {'function': 'first_item', 'args': ([99],), 'expected': 99, 'public': False},
    'last-item-public': {'function': 'last_item', 'args': ([4, 8, 12],), 'expected': 12, 'public': False},
    'last-item-empty': {'function': 'last_item', 'args': ([],), 'expected': None, 'public': False},
    'last-item-other': {'function': 'last_item', 'args': (['a', 'b'],), 'expected': 'b', 'public': False},
    'lookup-public': {'function': 'lookup_grade', 'args': ({'Aki': 92, 'Mina': 85}, 'Mina'), 'expected': 85, 'public': True},
    'lookup-missing-key': {'function': 'lookup_grade', 'args': ({}, 'Mina'), 'expected': 0, 'public': False},
    'lookup-other-key': {'function': 'lookup_grade', 'args': ({'Aki': 92, 'Mina': 85, 'Ren': 78}, 'Ren'), 'expected': 78, 'public': False},
    'price-public': {'function': 'lookup_price', 'args': ({'pen': 3, 'book': 12}, 'book'), 'expected': 12, 'public': False},
    'price-missing': {'function': 'lookup_price', 'args': ({}, 'book'), 'expected': -1, 'public': False},
    'price-other': {'function': 'lookup_price', 'args': ({'pen': 3, 'book': 12, 'bag': 20}, 'bag'), 'expected': 20, 'public': False},
    'double-public': {
        'function': 'double_numbers',
        'args': ([1, 3],),
        'expected': [2, 6],
        'public': True,
    },
    'empty-list': {
        'function': 'double_numbers',
        'args': ([],),
        'expected': [],
        'public': False,
    },
    'negative-values': {
        'function': 'double_numbers',
        'args': ([-2, 0, 5],),
        'expected': [-4, 0, 10],
        'public': False,
    },
    'empty-words': {
        'function': 'word_lengths',
        'args': ([],),
        'expected': [],
        'public': False,
    },
    'mixed-word-lengths': {
        'function': 'word_lengths',
        'args': (['a', 'loop', 'python'],),
        'expected': [1, 4, 6],
        'public': False,
    },
    'square-public': {
        'function': 'square_numbers',
        'args': ([2, -3],),
        'expected': [4, 9],
        'public': True,
    },
    'empty-square': {
        'function': 'square_numbers',
        'args': ([],),
        'expected': [],
        'public': False,
    },
    'zero-square': {
        'function': 'square_numbers',
        'args': ([0, 4],),
        'expected': [0, 16],
        'public': False,
    },
    'empty-negate': {
        'function': 'negate_numbers',
        'args': ([],),
        'expected': [],
        'public': False,
    },
    'mixed-negate': {
        'function': 'negate_numbers',
        'args': ([-2, 0, 5],),
        'expected': [2, 0, -5],
        'public': False,
    },
    'increment-public': {
        'function': 'increment_numbers',
        'args': ([1, 3],),
        'expected': [2, 4],
        'public': True,
    },
    'empty-increment': {
        'function': 'increment_numbers',
        'args': ([],),
        'expected': [],
        'public': False,
    },
    'negative-increment': {
        'function': 'increment_numbers',
        'args': ([-2, 0],),
        'expected': [-1, 1],
        'public': False,
    },
    'empty-absolute': {
        'function': 'absolute_numbers',
        'args': ([],),
        'expected': [],
        'public': False,
    },
    'mixed-absolute': {
        'function': 'absolute_numbers',
        'args': ([-3, 0, 4],),
        'expected': [3, 0, 4],
        'public': False,
    },
}

# Catalog cases for the additional beginner-Python topic families. Transfer
# cases intentionally remain hidden so the new task cannot be copied from the
# public exercise example.
TEST_CATALOG.update({
    'classify-number-public': {'function': 'classify_number', 'args': (4,), 'expected': 'positive', 'public': True},
    'classify-number-zero': {'function': 'classify_number', 'args': (0,), 'expected': 'zero', 'public': False},
    'classify-number-negative': {'function': 'classify_number', 'args': (-7,), 'expected': 'negative', 'public': False},
    'is-even-true': {'function': 'is_even', 'args': (6,), 'expected': True, 'public': False},
    'is-even-false': {'function': 'is_even', 'args': (3,), 'expected': False, 'public': False},
    'is-even-zero': {'function': 'is_even', 'args': (0,), 'expected': True, 'public': False},
    'rectangle-area-public': {'function': 'rectangle_area', 'args': (3, 4), 'expected': 12, 'public': True},
    'rectangle-area-zero': {'function': 'rectangle_area', 'args': (0, 8), 'expected': 0, 'public': False},
    'rectangle-area-other': {'function': 'rectangle_area', 'args': (5, 2), 'expected': 10, 'public': False},
    'rectangle-perimeter-public': {'function': 'rectangle_perimeter', 'args': (3, 4), 'expected': 14, 'public': False},
    'rectangle-perimeter-zero': {'function': 'rectangle_perimeter', 'args': (0, 8), 'expected': 16, 'public': False},
    'rectangle-perimeter-other': {'function': 'rectangle_perimeter', 'args': (5, 2), 'expected': 14, 'public': False},
    'sum-list-public': {'function': 'sum_numbers', 'args': ([2, 3, 4],), 'expected': 9, 'public': True},
    'sum-list-empty': {'function': 'sum_numbers', 'args': ([],), 'expected': 0, 'public': False},
    'sum-list-negative': {'function': 'sum_numbers', 'args': ([-2, 5, -1],), 'expected': 2, 'public': False},
    'count-positive-public': {'function': 'count_positive', 'args': ([1, -2, 3, 0],), 'expected': 2, 'public': False},
    'count-positive-none': {'function': 'count_positive', 'args': ([-2, 0],), 'expected': 0, 'public': False},
    'count-positive-mixed': {'function': 'count_positive', 'args': ([4, 1, -3],), 'expected': 2, 'public': False},
    'matrix-total-public': {'function': 'matrix_total', 'args': ([[1, 2], [3, 4]],), 'expected': 10, 'public': True},
    'matrix-total-empty': {'function': 'matrix_total', 'args': ([],), 'expected': 0, 'public': False},
    'matrix-total-uneven': {'function': 'matrix_total', 'args': ([[1], [2, 3], []],), 'expected': 6, 'public': False},
    'matrix-nonzero-public': {'function': 'count_nonzero', 'args': ([[1, 0], [0, 4]],), 'expected': 2, 'public': False},
    'matrix-nonzero-empty': {'function': 'count_nonzero', 'args': ([],), 'expected': 0, 'public': False},
    'matrix-nonzero-mixed': {'function': 'count_nonzero', 'args': ([[0, 2], [-1, 0]],), 'expected': 2, 'public': False},
    'reverse-string-public': {'function': 'reverse_text', 'args': ('cat',), 'expected': 'tac', 'public': True},
    'reverse-string-empty': {'function': 'reverse_text', 'args': ('',), 'expected': '', 'public': False},
    'reverse-string-unicode': {'function': 'reverse_text', 'args': ('xin',), 'expected': 'nix', 'public': False},
    'uppercase-string-public': {'function': 'uppercase_text', 'args': ('Hello',), 'expected': 'HELLO', 'public': False},
    'uppercase-string-empty': {'function': 'uppercase_text', 'args': ('',), 'expected': '', 'public': False},
    'uppercase-string-mixed': {'function': 'uppercase_text', 'args': ('PyThOn',), 'expected': 'PYTHON', 'public': False},
    'triple-numbers-public': {'function': 'triple_numbers', 'args': ([1, 3],), 'expected': [3, 9], 'public': True},
    'triple-numbers-empty': {'function': 'triple_numbers', 'args': ([],), 'expected': [], 'public': False},
    'triple-numbers-negative': {'function': 'triple_numbers', 'args': ([-2, 0, 5],), 'expected': [-6, 0, 15], 'public': False},
    'add-five-public': {'function': 'add_five_numbers', 'args': ([1, 3],), 'expected': [6, 8], 'public': False},
    'add-five-empty': {'function': 'add_five_numbers', 'args': ([],), 'expected': [], 'public': False},
    'add-five-negative': {'function': 'add_five_numbers', 'args': ([-2, 0],), 'expected': [3, 5], 'public': False},
    'factorial-public': {'function': 'factorial', 'args': (4,), 'expected': 24, 'public': True},
    'factorial-zero': {'function': 'factorial', 'args': (0,), 'expected': 1, 'public': False},
    'factorial-one': {'function': 'factorial', 'args': (1,), 'expected': 1, 'public': False},
    'sum-to-n-public': {'function': 'sum_to_n', 'args': (4,), 'expected': 10, 'public': False},
    'sum-to-n-zero': {'function': 'sum_to_n', 'args': (0,), 'expected': 0, 'public': False},
    'sum-to-n-other': {'function': 'sum_to_n', 'args': (6,), 'expected': 21, 'public': False},
})

TEST_CATALOG.update({
    'binary-search-public': {'function': 'binary_search', 'args': ([1, 3, 5, 7], 5), 'expected': 2, 'public': True},
    'binary-search-missing': {'function': 'binary_search', 'args': ([1, 3, 5, 7], 4), 'expected': -1, 'public': False},
    'binary-search-single': {'function': 'binary_search', 'args': ([8], 8), 'expected': 0, 'public': False},
    'first-geq-public': {'function': 'first_geq', 'args': ([1, 3, 5, 7], 4), 'expected': 2, 'public': False},
    'first-geq-none': {'function': 'first_geq', 'args': ([1, 3, 5], 8), 'expected': -1, 'public': False},
    'first-geq-duplicate': {'function': 'first_geq', 'args': ([1, 3, 3, 3, 8], 3), 'expected': 1, 'public': False},
    'valid-brackets-public': {'function': 'valid_brackets', 'args': ('([])',), 'expected': True, 'public': True},
    'valid-brackets-unclosed': {'function': 'valid_brackets', 'args': ('([)',), 'expected': False, 'public': False},
    'valid-brackets-wrong-order': {'function': 'valid_brackets', 'args': ('([)]',), 'expected': False, 'public': False},
    'remove-adjacent-public': {'function': 'remove_adjacent_duplicates', 'args': ('abbaca',), 'expected': 'ca', 'public': False},
    'remove-adjacent-empty': {'function': 'remove_adjacent_duplicates', 'args': ('',), 'expected': '', 'public': False},
    'remove-adjacent-chain': {'function': 'remove_adjacent_duplicates', 'args': ('azxxzy',), 'expected': 'ay', 'public': False},
    'rotate-queue-public': {'function': 'rotate_queue', 'args': (['A', 'B', 'C'],), 'expected': ['B', 'C', 'A'], 'public': True},
    'rotate-queue-empty': {'function': 'rotate_queue', 'args': ([],), 'expected': [], 'public': False},
    'rotate-queue-single': {'function': 'rotate_queue', 'args': (['A'],), 'expected': ['A'], 'public': False},
    'queue-front-public': {'function': 'queue_front', 'args': (['A', 'B'],), 'expected': 'A', 'public': False},
    'queue-front-empty': {'function': 'queue_front', 'args': ([],), 'expected': None, 'public': False},
    'queue-front-other': {'function': 'queue_front', 'args': ([4, 8],), 'expected': 4, 'public': False},
    'selection-sort-public': {'function': 'selection_sort', 'args': ([3, 1, 2],), 'expected': [1, 2, 3], 'public': True},
    'selection-sort-empty': {'function': 'selection_sort', 'args': ([],), 'expected': [], 'public': False},
    'selection-sort-duplicates': {'function': 'selection_sort', 'args': ([3, 1, 3, 2],), 'expected': [1, 2, 3, 3], 'public': False},
    'sort-descending-public': {'function': 'sort_descending', 'args': ([3, 1, 2],), 'expected': [3, 2, 1], 'public': False},
    'sort-descending-empty': {'function': 'sort_descending', 'args': ([],), 'expected': [], 'public': False},
    'sort-descending-duplicates': {'function': 'sort_descending', 'args': ([3, 1, 3, 2],), 'expected': [3, 3, 2, 1], 'public': False},
    'two-sum-public': {'function': 'two_sum_indexes', 'args': ([2, 7, 11, 15], 9), 'expected': [0, 1], 'public': True},
    'two-sum-duplicate': {'function': 'two_sum_indexes', 'args': ([3, 3], 6), 'expected': [0, 1], 'public': False},
    'two-sum-missing': {'function': 'two_sum_indexes', 'args': ([1, 2, 4], 8), 'expected': [-1, -1], 'public': False},
    'first-duplicate-public': {'function': 'first_duplicate', 'args': ([2, 1, 3, 1, 2],), 'expected': 1, 'public': False},
    'first-duplicate-none': {'function': 'first_duplicate', 'args': ([1, 2, 3],), 'expected': None, 'public': False},
    'first-duplicate-other': {'function': 'first_duplicate', 'args': ([5, 5, 4],), 'expected': 5, 'public': False},
    'graph-path-public': {'function': 'has_path', 'args': ({'A': ['B'], 'B': ['C'], 'C': []}, 'A', 'C'), 'expected': True, 'public': True},
    'graph-path-missing': {'function': 'has_path', 'args': ({'A': ['B'], 'B': [], 'C': []}, 'A', 'C'), 'expected': False, 'public': False},
    'graph-path-cycle': {'function': 'has_path', 'args': ({'A': ['B'], 'B': ['A', 'C'], 'C': []}, 'A', 'C'), 'expected': True, 'public': False},
    'reachable-count-public': {'function': 'reachable_count', 'args': ({'A': ['B', 'C'], 'B': ['D'], 'C': [], 'D': []}, 'A'), 'expected': 4, 'public': False},
    'reachable-count-isolated': {'function': 'reachable_count', 'args': ({'A': [], 'B': []}, 'A'), 'expected': 1, 'public': False},
    'reachable-count-cycle': {'function': 'reachable_count', 'args': ({'A': ['B'], 'B': ['C'], 'C': ['A']}, 'A'), 'expected': 3, 'public': False},
    'climb-stairs-public': {'function': 'climb_stairs', 'args': (4,), 'expected': 5, 'public': True},
    'climb-stairs-zero': {'function': 'climb_stairs', 'args': (0,), 'expected': 1, 'public': False},
    'climb-stairs-other': {'function': 'climb_stairs', 'args': (6,), 'expected': 13, 'public': False},
    'fibonacci-public': {'function': 'fibonacci_n', 'args': (6,), 'expected': 8, 'public': False},
    'fibonacci-zero': {'function': 'fibonacci_n', 'args': (0,), 'expected': 0, 'public': False},
    'fibonacci-other': {'function': 'fibonacci_n', 'args': (8,), 'expected': 21, 'public': False},
    'leap-year-public': {'function': 'is_leap_year', 'args': (2024,), 'expected': True, 'public': True},
    'leap-year-century': {'function': 'is_leap_year', 'args': (1900,), 'expected': False, 'public': False},
    'leap-year-four-hundred': {'function': 'is_leap_year', 'args': (2000,), 'expected': True, 'public': False},
    'score-label-a': {'function': 'score_label', 'args': (95,), 'expected': 'A', 'public': False},
    'score-label-b': {'function': 'score_label', 'args': (84,), 'expected': 'B', 'public': False},
    'score-label-c': {'function': 'score_label', 'args': (79,), 'expected': 'C', 'public': False},
    'palindrome-public': {'function': 'is_palindrome', 'args': ('level',), 'expected': True, 'public': True},
    'palindrome-false': {'function': 'is_palindrome', 'args': ('python',), 'expected': False, 'public': False},
    'palindrome-empty': {'function': 'is_palindrome', 'args': ('',), 'expected': True, 'public': False},
    'vowel-count-public': {'function': 'count_vowels', 'args': ('Apple',), 'expected': 2, 'public': False},
    'vowel-count-none': {'function': 'count_vowels', 'args': ('rhythm',), 'expected': 0, 'public': False},
    'vowel-count-mixed': {'function': 'count_vowels', 'args': ('AEiou',), 'expected': 5, 'public': False},
    'power-two-public': {'function': 'power_of_two', 'args': (5,), 'expected': 32, 'public': True},
    'power-two-zero': {'function': 'power_of_two', 'args': (0,), 'expected': 1, 'public': False},
    'power-two-one': {'function': 'power_of_two', 'args': (1,), 'expected': 2, 'public': False},
    'odd-sum-public': {'function': 'odd_sum', 'args': (4,), 'expected': 16, 'public': False},
    'odd-sum-zero': {'function': 'odd_sum', 'args': (0,), 'expected': 0, 'public': False},
    'odd-sum-other': {'function': 'odd_sum', 'args': (6,), 'expected': 36, 'public': False},
    'first-binary-public': {'function': 'first_binary_search', 'args': ([1, 2, 2, 2, 3], 2), 'expected': 1, 'public': True},
    'first-binary-missing': {'function': 'first_binary_search', 'args': ([1, 3, 5], 4), 'expected': -1, 'public': False},
    'first-binary-later': {'function': 'first_binary_search', 'args': ([1, 2, 4, 4, 4, 9], 4), 'expected': 2, 'public': False},
    'last-binary-public': {'function': 'last_binary_search', 'args': ([1, 2, 2, 2, 3], 2), 'expected': 3, 'public': False},
    'last-binary-missing': {'function': 'last_binary_search', 'args': ([1, 3, 5], 4), 'expected': -1, 'public': False},
    'last-binary-duplicate': {'function': 'last_binary_search', 'args': ([1, 4, 4, 4, 8], 4), 'expected': 3, 'public': False},
    'insertion-sort-public': {'function': 'insertion_sort', 'args': ([3, 1, 2],), 'expected': [1, 2, 3], 'public': True},
    'insertion-sort-empty': {'function': 'insertion_sort', 'args': ([],), 'expected': [], 'public': False},
    'insertion-sort-duplicates': {'function': 'insertion_sort', 'args': ([3, 1, 3, 2],), 'expected': [1, 2, 3, 3], 'public': False},
    'merge-sorted-public': {'function': 'merge_sorted', 'args': ([1, 4], [2, 3]), 'expected': [1, 2, 3, 4], 'public': False},
    'merge-sorted-empty': {'function': 'merge_sorted', 'args': ([], [2, 3]), 'expected': [2, 3], 'public': False},
    'merge-sorted-other': {'function': 'merge_sorted', 'args': ([1, 1, 5], [1, 2]), 'expected': [1, 1, 1, 2, 5], 'public': False},
    'char-frequency-public': {'function': 'character_frequencies', 'args': ('banana',), 'expected': {'b': 1, 'a': 3, 'n': 2}, 'public': True},
    'char-frequency-empty': {'function': 'character_frequencies', 'args': ('',), 'expected': {}, 'public': False},
    'char-frequency-other': {'function': 'character_frequencies', 'args': ('aab',), 'expected': {'a': 2, 'b': 1}, 'public': False},
    'unique-char-public': {'function': 'has_unique_characters', 'args': ('abc',), 'expected': True, 'public': False},
    'unique-char-false': {'function': 'has_unique_characters', 'args': ('hello',), 'expected': False, 'public': False},
    'unique-char-empty': {'function': 'has_unique_characters', 'args': ('',), 'expected': True, 'public': False},
    'shortest-path-public': {'function': 'shortest_path_length', 'args': ({'A': ['B'], 'B': ['C'], 'C': []}, 'A', 'C'), 'expected': 2, 'public': True},
    'shortest-path-missing': {'function': 'shortest_path_length', 'args': ({'A': ['B'], 'B': [], 'C': []}, 'A', 'C'), 'expected': -1, 'public': False},
    'shortest-path-cycle': {'function': 'shortest_path_length', 'args': ({'A': ['B', 'C'], 'B': ['A'], 'C': []}, 'A', 'C'), 'expected': 1, 'public': False},
    'reachable-list-public': {'function': 'reachable_nodes', 'args': ({'A': ['B', 'C'], 'B': ['D'], 'C': [], 'D': []}, 'A'), 'expected': ['A', 'B', 'C', 'D'], 'public': False},
    'reachable-list-isolated': {'function': 'reachable_nodes', 'args': ({'A': [], 'B': []}, 'A'), 'expected': ['A'], 'public': False},
    'reachable-list-cycle': {'function': 'reachable_nodes', 'args': ({'A': ['B'], 'B': ['C'], 'C': ['A']}, 'A'), 'expected': ['A', 'B', 'C'], 'public': False},
    'min-cost-public': {'function': 'min_cost_climbing_stairs', 'args': ([10, 15, 20],), 'expected': 15, 'public': True},
    'min-cost-empty': {'function': 'min_cost_climbing_stairs', 'args': ([],), 'expected': 0, 'public': False},
    'min-cost-other': {'function': 'min_cost_climbing_stairs', 'args': ([1, 100, 1, 1, 1, 100, 1, 1, 100, 1],), 'expected': 6, 'public': False},
    'tribonacci-public': {'function': 'tribonacci', 'args': (4,), 'expected': 4, 'public': False},
    'tribonacci-zero': {'function': 'tribonacci', 'args': (0,), 'expected': 0, 'public': False},
    'tribonacci-other': {'function': 'tribonacci', 'args': (7,), 'expected': 24, 'public': False},
})

TEST_CATALOG.update({
    'unique-sorted-public': {'function': 'unique_sorted_numbers', 'args': ([3, 1, 3, 2],), 'expected': [1, 2, 3], 'public': True},
    'unique-sorted-empty': {'function': 'unique_sorted_numbers', 'args': ([],), 'expected': [], 'public': False},
    'unique-sorted-negative': {'function': 'unique_sorted_numbers', 'args': ([-1, -3, -1, 0],), 'expected': [-3, -1, 0], 'public': False},
    'common-numbers-public': {'function': 'common_numbers', 'args': ([3, 1, 2], [2, 4, 3]), 'expected': [2, 3], 'public': False},
    'common-numbers-empty': {'function': 'common_numbers', 'args': ([], [1]), 'expected': [], 'public': False},
    'common-numbers-other': {'function': 'common_numbers', 'args': ([1, 1, 5], [5, 5, 1]), 'expected': [1, 5], 'public': False},
    'set-membership-public': {'function': 'count_allowed', 'args': ([1, 2, 4, 2], [2, 3]), 'expected': 2, 'public': True},
    'set-membership-none': {'function': 'count_allowed', 'args': ([1, 4], [2, 3]), 'expected': 0, 'public': False},
    'set-membership-other': {'function': 'count_allowed', 'args': ([3, 3, 5, 7], [3, 7]), 'expected': 3, 'public': False},
    'missing-numbers-public': {'function': 'missing_numbers', 'args': ([1, 2, 3], [2]), 'expected': [1, 3], 'public': False},
    'missing-numbers-empty': {'function': 'missing_numbers', 'args': ([], [1]), 'expected': [], 'public': False},
    'missing-numbers-other': {'function': 'missing_numbers', 'args': ([4, 2, 2], [2, 5]), 'expected': [4], 'public': False},
    'even-squares-public': {'function': 'even_squares', 'args': ([1, 2, 3, 4],), 'expected': [4, 16], 'public': True},
    'even-squares-empty': {'function': 'even_squares', 'args': ([],), 'expected': [], 'public': False},
    'even-squares-negative': {'function': 'even_squares', 'args': ([-3, -2, 0, 5],), 'expected': [4, 0], 'public': False},
    'uppercase-words-public': {'function': 'uppercase_long_words', 'args': (['cat', 'python', 'code'],), 'expected': ['PYTHON', 'CODE'], 'public': False},
    'uppercase-words-empty': {'function': 'uppercase_long_words', 'args': ([],), 'expected': [], 'public': False},
    'uppercase-words-other': {'function': 'uppercase_long_words', 'args': (['four', 'a', 'FIVE'],), 'expected': ['FOUR', 'FIVE'], 'public': False},
    'word-lengths-public': {'function': 'word_lengths', 'args': (['hi', 'python'],), 'expected': [2, 6], 'public': True},
    'word-lengths-empty': {'function': 'word_lengths', 'args': ([],), 'expected': [], 'public': False},
    'word-lengths-other': {'function': 'word_lengths', 'args': (['a', '', 'abc'],), 'expected': [1, 0, 3], 'public': False},
    'positive-numbers-public': {'function': 'positive_numbers', 'args': ([-1, 0, 2, 3],), 'expected': [2, 3], 'public': False},
    'positive-numbers-empty': {'function': 'positive_numbers', 'args': ([],), 'expected': [], 'public': False},
    'positive-numbers-other': {'function': 'positive_numbers', 'args': ([-2, 0],), 'expected': [], 'public': False},
    'safe-int-public': {'function': 'safe_to_int', 'args': ('42',), 'expected': 42, 'public': True},
    'safe-int-invalid': {'function': 'safe_to_int', 'args': ('four',), 'expected': None, 'public': False},
    'safe-int-negative': {'function': 'safe_to_int', 'args': ('-7',), 'expected': -7, 'public': False},
    'safe-index-public': {'function': 'safe_get_item', 'args': (['a', 'b'], 1), 'expected': 'b', 'public': False},
    'safe-index-negative': {'function': 'safe_get_item', 'args': (['a', 'b'], -1), 'expected': 'b', 'public': False},
    'safe-index-outside': {'function': 'safe_get_item', 'args': (['a'], 4), 'expected': None, 'public': False},
    'safe-dict-number-public': {'function': 'safe_dictionary_number', 'args': ({'age': '12'}, 'age'), 'expected': 12, 'public': True},
    'safe-dict-number-missing': {'function': 'safe_dictionary_number', 'args': ({}, 'age'), 'expected': None, 'public': False},
    'safe-dict-number-invalid': {'function': 'safe_dictionary_number', 'args': ({'age': 'old'}, 'age'), 'expected': None, 'public': False},
    'safe-reciprocal-public': {'function': 'safe_reciprocal', 'args': ('4',), 'expected': 0.25, 'public': False},
    'safe-reciprocal-zero': {'function': 'safe_reciprocal', 'args': ('0',), 'expected': None, 'public': False},
    'safe-reciprocal-invalid': {'function': 'safe_reciprocal', 'args': ('x',), 'expected': None, 'public': False},
    'prime-public': {'function': 'is_prime', 'args': (29,), 'expected': True, 'public': True},
    'prime-one': {'function': 'is_prime', 'args': (1,), 'expected': False, 'public': False},
    'prime-composite': {'function': 'is_prime', 'args': (21,), 'expected': False, 'public': False},
    'gcd-public': {'function': 'greatest_common_divisor', 'args': (48, 18), 'expected': 6, 'public': False},
    'gcd-zero': {'function': 'greatest_common_divisor', 'args': (0, 5), 'expected': 5, 'public': False},
    'gcd-other': {'function': 'greatest_common_divisor', 'args': (21, 14), 'expected': 7, 'public': False},
    'digit-sum-public': {'function': 'digit_sum', 'args': (482,), 'expected': 14, 'public': True},
    'digit-sum-zero': {'function': 'digit_sum', 'args': (0,), 'expected': 0, 'public': False},
    'digit-sum-other': {'function': 'digit_sum', 'args': (1009,), 'expected': 10, 'public': False},
    'digit-count-public': {'function': 'digit_count', 'args': (482,), 'expected': 3, 'public': False},
    'digit-count-zero': {'function': 'digit_count', 'args': (0,), 'expected': 1, 'public': False},
    'digit-count-other': {'function': 'digit_count', 'args': (1009,), 'expected': 4, 'public': False},
    'pair-sum-public': {'function': 'has_pair_sum', 'args': ([1, 2, 4, 7], 9), 'expected': True, 'public': True},
    'pair-sum-missing': {'function': 'has_pair_sum', 'args': ([1, 2, 4, 7], 6), 'expected': False, 'public': False},
    'pair-sum-duplicate': {'function': 'has_pair_sum', 'args': ([2, 2], 4), 'expected': True, 'public': False},
    'pointer-palindrome-public': {'function': 'pointer_palindrome', 'args': ('level',), 'expected': True, 'public': False},
    'pointer-palindrome-false': {'function': 'pointer_palindrome', 'args': ('python',), 'expected': False, 'public': False},
    'pointer-palindrome-empty': {'function': 'pointer_palindrome', 'args': ('',), 'expected': True, 'public': False},
    'remove-duplicates-public': {'function': 'remove_sorted_duplicates', 'args': ([1, 1, 2, 2, 3],), 'expected': [1, 2, 3], 'public': True},
    'remove-duplicates-empty': {'function': 'remove_sorted_duplicates', 'args': ([],), 'expected': [], 'public': False},
    'remove-duplicates-other': {'function': 'remove_sorted_duplicates', 'args': ([1, 1, 1],), 'expected': [1], 'public': False},
    'sorted-squares-public': {'function': 'sorted_squares', 'args': ([-4, -1, 0, 3, 10],), 'expected': [0, 1, 9, 16, 100], 'public': False},
    'sorted-squares-empty': {'function': 'sorted_squares', 'args': ([],), 'expected': [], 'public': False},
    'sorted-squares-other': {'function': 'sorted_squares', 'args': ([-2, -1],), 'expected': [1, 4], 'public': False},
    'window-sum-public': {'function': 'maximum_window_sum', 'args': ([2, 1, 5, 1, 3, 2], 3), 'expected': 9, 'public': True},
    'window-sum-zero': {'function': 'maximum_window_sum', 'args': ([1, 2], 0), 'expected': 0, 'public': False},
    'window-sum-other': {'function': 'maximum_window_sum', 'args': ([2, -1, 2, 3], 2), 'expected': 5, 'public': False},
    'window-average-public': {'function': 'maximum_window_average', 'args': ([1, 12, -5, -6, 50, 3], 4), 'expected': 12.75, 'public': False},
    'window-average-zero': {'function': 'maximum_window_average', 'args': ([1, 2], 0), 'expected': 0, 'public': False},
    'window-average-other': {'function': 'maximum_window_average', 'args': ([5, 1, 4], 2), 'expected': 3.0, 'public': False},
    'longest-unique-public': {'function': 'longest_unique_length', 'args': ('abcabcbb',), 'expected': 3, 'public': True},
    'longest-unique-empty': {'function': 'longest_unique_length', 'args': ('',), 'expected': 0, 'public': False},
    'longest-unique-other': {'function': 'longest_unique_length', 'args': ('pwwkew',), 'expected': 3, 'public': False},
    'two-distinct-public': {'function': 'longest_two_distinct_length', 'args': ('eceba',), 'expected': 3, 'public': False},
    'two-distinct-empty': {'function': 'longest_two_distinct_length', 'args': ('',), 'expected': 0, 'public': False},
    'two-distinct-other': {'function': 'longest_two_distinct_length', 'args': ('ccaabbb',), 'expected': 5, 'public': False},
    'coin-count-public': {'function': 'minimum_coin_count', 'args': (41,), 'expected': 4, 'public': True},
    'coin-count-zero': {'function': 'minimum_coin_count', 'args': (0,), 'expected': 0, 'public': False},
    'coin-count-other': {'function': 'minimum_coin_count', 'args': (99,), 'expected': 9, 'public': False},
    'change-breakdown-public': {'function': 'change_breakdown', 'args': (41,), 'expected': [25, 10, 5, 1], 'public': False},
    'change-breakdown-zero': {'function': 'change_breakdown', 'args': (0,), 'expected': [], 'public': False},
    'change-breakdown-other': {'function': 'change_breakdown', 'args': (30,), 'expected': [25, 5], 'public': False},
    'activities-public': {'function': 'maximum_activities', 'args': ([[1, 3], [2, 4], [3, 5], [5, 6]],), 'expected': 3, 'public': True},
    'activities-empty': {'function': 'maximum_activities', 'args': ([],), 'expected': 0, 'public': False},
    'activities-other': {'function': 'maximum_activities', 'args': ([[5, 7], [1, 2], [2, 5], [6, 8]],), 'expected': 3, 'public': False},
    'chosen-intervals-public': {'function': 'choose_activities', 'args': ([[1, 3], [2, 4], [3, 5], [5, 6]],), 'expected': [[1, 3], [3, 5], [5, 6]], 'public': False},
    'chosen-intervals-empty': {'function': 'choose_activities', 'args': ([],), 'expected': [], 'public': False},
    'chosen-intervals-other': {'function': 'choose_activities', 'args': ([[5, 7], [1, 2], [2, 5], [6, 8]],), 'expected': [[1, 2], [2, 5], [5, 7]], 'public': False},
    'subsets-public': {'function': 'generate_subsets', 'args': ([1, 2],), 'expected': [[], [1], [2], [1, 2]], 'public': True},
    'subsets-empty': {'function': 'generate_subsets', 'args': ([],), 'expected': [[]], 'public': False},
    'subsets-other': {'function': 'generate_subsets', 'args': ([1, 2, 3],), 'expected': [[], [1], [2], [3], [1, 2], [1, 3], [2, 3], [1, 2, 3]], 'public': False},
    'binary-strings-public': {'function': 'binary_strings', 'args': (2,), 'expected': ['00', '01', '10', '11'], 'public': False},
    'binary-strings-zero': {'function': 'binary_strings', 'args': (0,), 'expected': [''], 'public': False},
    'binary-strings-other': {'function': 'binary_strings', 'args': (1,), 'expected': ['0', '1'], 'public': False},
    'parentheses-public': {'function': 'generate_parentheses', 'args': (2,), 'expected': ['(())', '()()'], 'public': True},
    'parentheses-zero': {'function': 'generate_parentheses', 'args': (0,), 'expected': [''], 'public': False},
    'parentheses-other': {'function': 'generate_parentheses', 'args': (3,), 'expected': ['((()))', '(()())', '(())()', '()(())', '()()()'], 'public': False},
    'letter-combinations-public': {'function': 'letter_combinations', 'args': (['ab', '12'],), 'expected': ['a1', 'a2', 'b1', 'b2'], 'public': False},
    'letter-combinations-empty': {'function': 'letter_combinations', 'args': ([],), 'expected': [''], 'public': False},
    'letter-combinations-other': {'function': 'letter_combinations', 'args': (['x', 'yz'],), 'expected': ['xy', 'xz'], 'public': False},
})


def _bulk_mode_cases(mode, index):
    """Return public, boundary, and mixed cases for one reviewed drill mode."""
    cases = {
        'conditional': [((-index,), 'negative'), ((0,), 'zero'), ((index,), 'positive')],
        'function': [((index, 2), index * 2), ((0, index), 0), ((-index, 3), -index * 3)],
        'list': [(([index, 2, 3],), index + 5), (([],), 0), (([-index, 0, index],), 0)],
        'string': [(('code',), 'edoc'), (('',), ''), ((f'a{index}b',), f'b{index}a')],
        'loop': [(([index, 3],), [index + 1, 4]), (([],), []), (([-1, 0],), [0, 1])],
        'recursion': [((index,), index * (index + 1) // 2), ((0,), 0), ((3,), 6)],
        'dictionary': [(({'a': index}, 'a'), index), (({}, 'a'), None), (({'a': 1}, 'x'), None)],
        'search': [(([1, 3, 5, 7], 5), 2), (([1, 3, 5], 4), -1), (([index], index), 0)],
        'stack': [(('(())',), True), (('(()',), False), (('())(',), False)],
        'sorting': [(([3, 1, 2],), [1, 2, 3]), (([],), []), (([3, 1, 3],), [1, 3, 3])],
        'hash': [(([2, 1, 2],), 2), (([1, 2, 3],), None), (([index, 4, 4],), 4)],
        'graph': [(({'A': ['B'], 'B': []}, 'A'), 2), (({'A': []}, 'A'), 1), (({'A': ['B'], 'B': ['A']}, 'A'), 2)],
        'dp': [((6,), 8), ((0,), 0), ((index,), _fibonacci(index))],
        'set': [(([2, 1, 2],), [1, 2]), (([],), []), (([index, 1, index],), sorted({index, 1}))],
        'comprehension': [(([1, 2, 3, 4],), [4, 16]), (([],), []), (([-2, -1, 0],), [4, 0])],
        'exception': [(('42',), 42), (('bad',), None), ((str(-index),), -index)],
        'numeric': [((482,), 14), ((0,), 0), ((1000 + index,), 1 + index)],
        'two-pointer': [(([1, 2, 4, 7], 9), True), (([1, 2, 4, 7], 6), False), (([2, 2], 4), True)],
        'window': [(([2, 1, 5, 1], 2), 6), (([1, 2], 0), 0), (([2, -1, 2, 3], 2), 5)],
        'greedy': [((41,), 4), ((0,), 0), ((99,), 9)],
        'backtracking': [((2,), ['00', '01', '10', '11']), ((0,), ['']), ((1,), ['0', '1'])],
    }
    return cases[mode]


def _fibonacci(number):
    previous, current = 0, 1
    for _ in range(number):
        previous, current = current, previous + current
    return previous


def _add_bulk_practice_cases():
    for _topic_slug, _topic_name, _concept, _misconception, existing_count, mode in BULK_SERIES:
        for level_number in range(existing_count + 1, 11):
            slug = f'{_topic_slug}-practice-{level_number}'
            cases = _bulk_mode_cases(mode, level_number)
            for suffix, case, is_public in zip(('public', 'boundary', 'mixed'), cases, (True, False, False)):
                args, expected = case
                TEST_CATALOG[f'{slug}-{suffix}'] = {
                    'function': 'solve', 'args': args, 'expected': expected, 'public': is_public,
                }
            for suffix, case in zip(('public', 'boundary', 'mixed'), reversed(cases)):
                args, expected = case
                TEST_CATALOG[f'{slug}-transfer-{suffix}'] = {
                    'function': 'transfer_solve', 'args': args, 'expected': expected, 'public': False,
                }


_add_bulk_practice_cases()

EXECUTION_SECONDS = 2


class ExecutionTimedOut(Exception):
    pass


def _timeout_handler(signum, frame):
    raise ExecutionTimedOut


def _start_timeout():
    if hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(EXECUTION_SECONDS)


def _cancel_timeout():
    if hasattr(signal, 'SIGALRM'):
        signal.alarm(0)


def _result(status, message, tests=()):
    return {'status': status, 'message': message, 'tests': list(tests)}


def _run_learner(source_code, test):
    worker_payload = json.dumps({
        'source_code': source_code,
        'function': test['function'],
        'args': test['args'],
    })
    worker_path = str(Path(__file__).with_name('worker.py'))
    process_options = {
        'input': worker_payload,
        'capture_output': True,
        'text': True,
        'timeout': EXECUTION_SECONDS,
        'check': False,
        'env': {'PATH': os.environ.get('PATH', ''), 'PYTHONDONTWRITEBYTECODE': '1'},
        'cwd': tempfile.gettempdir(),
    }
    if os.name == 'posix' and hasattr(os, 'geteuid') and os.geteuid() == 0:
        process_options.update(user=10001, group=10001)
    try:
        process = subprocess.run(
            [sys.executable, worker_path],
            **process_options,
        )
    except subprocess.TimeoutExpired:
        raise ExecutionTimedOut
    if process.returncode != 0:
        return {'kind': 'runtime_error', 'error_type': 'ProcessExit', 'message': 'Learner process exited unexpectedly.'}
    try:
        return json.loads(process.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {'kind': 'runtime_error', 'error_type': 'InvalidOutput', 'message': 'Learner process returned invalid output.'}


def execute(payload):
    source_code = payload.get('source_code')
    test_case_ids = payload.get('test_case_ids')
    if payload.get('language') != 'python':
        return _result('NOT_EXECUTED', 'The runner supports Python only.')
    if not isinstance(source_code, str) or not source_code.strip():
        return _result('NOT_EXECUTED', 'Source code is required.')
    if not isinstance(test_case_ids, list) or not test_case_ids:
        return _result('NOT_EXECUTED', 'At least one curated test-case ID is required.')
    if any(test_id not in TEST_CATALOG for test_id in test_case_ids):
        return _result('NOT_EXECUTED', 'The request contains an unknown test-case ID.')

    try:
        compiled = compile(source_code, 'learner_submission.py', 'exec')
    except SyntaxError as exc:
        clean_msg = str(exc.msg).replace('\n', ' ')[:160]
        return _result(
            'SYNTAX_ERROR',
            f'Syntax error on line {exc.lineno}: {clean_msg}',
        )

    _start_timeout()
    try:
        test_results = []
        for test_id in test_case_ids:
            test = TEST_CATALOG[test_id]
            worker_result = _run_learner(source_code, test)
            if worker_result.get('kind') == 'missing_function':
                return _result(
                    'LOGIC_ERROR',
                    f"Required function `{test['function']}` was not defined.",
                )
            if worker_result.get('kind') != 'ok':
                return _result(
                    'RUNTIME_ERROR',
                    f"{worker_result.get('error_type', 'RuntimeError')}: "
                    f"{worker_result.get('message', 'Learner code failed.')}",
                )
            actual = worker_result.get('value')
            passed = actual == test['expected']
            evidence = {'id': test_id, 'passed': passed}
            if test['public'] and not passed:
                evidence['expected'] = test['expected']
                evidence['actual'] = actual
            test_results.append(evidence)
            if not passed:
                message = (
                    'A public test returned an unexpected result.'
                    if test['public']
                    else 'A hidden boundary test failed.'
                )
                status = 'OUTPUT_MISMATCH' if test['public'] else 'LOGIC_ERROR'
                return _result(status, message, test_results)
    except ExecutionTimedOut:
        return _result('TIMEOUT', 'Execution exceeded the 2-second limit.')
    finally:
        _cancel_timeout()

    return _result('PASSED', 'All requested public and hidden tests passed.', test_results)


def main():
    safe_dumps = json.dumps
    try:
        payload = json.loads(sys.stdin.read())
        result = execute(payload)
    except (json.JSONDecodeError, TypeError):
        result = _result('NOT_EXECUTED', 'The runner received an invalid request.')
    sys.stdout.write(safe_dumps(result, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
