"""Shared definitions for the reviewed ten-exercises-per-topic practice series."""

PRACTICE_LEVELS = (
    'warm-up', 'boundary cases', 'mixed inputs', 'guided challenge',
    'applied challenge', 'review checkpoint', 'speed checkpoint', 'mastery drill',
)

BULK_SERIES = (
    ('python-conditionals', 'Python conditionals', 'conditionals', 'if-else-branch-misuse', 2, 'conditional'),
    ('python-functions', 'Python functions', 'function_basics', 'function-return-misuse', 2, 'function'),
    ('python-lists', 'Python lists', 'list_1d_operations', 'one-dimensional-list-misuse', 2, 'list'),
    ('python-strings', 'Python strings', 'string_operations', 'string-operation-misuse', 2, 'string'),
    ('python-loops', 'Python loops', 'loop_values', 'loop-value-misuse', 4, 'loop'),
    ('python-recursion', 'Python recursion', 'recursion', 'recursion-base-case-misuse', 2, 'recursion'),
    ('python-collections', 'Python collections', 'dictionary_keys', 'dictionary-key-misuse', 2, 'dictionary'),
    ('dsa-searching', 'DSA: Searching', 'binary_search', 'binary-search-boundary-misuse', 2, 'search'),
    ('dsa-linear-structures', 'DSA: Linear structures', 'stack', 'stack-order-misuse', 2, 'stack'),
    ('dsa-sorting', 'DSA: Sorting', 'sorting', 'sorting-invariant-misuse', 2, 'sorting'),
    ('dsa-hash-maps', 'DSA: Hash maps', 'hash_maps', 'hash-map-complement-misuse', 2, 'hash'),
    ('dsa-graphs', 'DSA: Graphs', 'graphs', 'graph-visited-misuse', 2, 'graph'),
    ('dsa-dynamic-programming', 'DSA: Dynamic programming', 'dynamic_programming', 'dynamic-programming-state-misuse', 2, 'dp'),
    ('python-sets', 'Python sets', 'set_operations', 'set-operation-misuse', 2, 'set'),
    ('python-comprehensions', 'Python comprehensions', 'list_comprehensions', 'comprehension-misuse', 2, 'comprehension'),
    ('python-exceptions', 'Python exception handling', 'exception_handling', 'exception-handling-misuse', 2, 'exception'),
    ('python-numeric-algorithms', 'Python numeric algorithms', 'numeric_algorithms', 'numeric-algorithm-misuse', 2, 'numeric'),
    ('dsa-two-pointers', 'DSA: Two pointers', 'two_pointers', 'two-pointer-misuse', 2, 'two-pointer'),
    ('dsa-sliding-window', 'DSA: Sliding window', 'sliding_window', 'sliding-window-misuse', 2, 'window'),
    ('dsa-greedy', 'DSA: Greedy algorithms', 'greedy_algorithms', 'greedy-choice-misuse', 2, 'greedy'),
    ('dsa-backtracking', 'DSA: Backtracking', 'backtracking', 'backtracking-misuse', 2, 'backtracking'),
)
