import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

# AI-generated problem/hint/explanation text mixes Japanese prose with raw
# LaTeX commands (e.g. "関数 f(x)=\frac{x^2\,e^{x}}{1+x^3} の x=1 における
# 導関数..."), sometimes with no delimiters of its own and sometimes
# already wrapped in \( \) (or \[ \], $$ $$) — the AI is never told to use
# LaTeX one way or the other, so its output is inconsistent. KaTeX (loaded
# in base.html) only renders text wrapped in a delimiter it's configured
# to look for, so this filter finds runs of LaTeX-looking syntax and wraps
# just those in \( \) for it — but first checks whether a run is already
# delimited (by any of the forms KaTeX is configured for) and leaves those
# alone, since wrapping an already-\(-delimited run in another \( \) is
# exactly what broke rendering (KaTeX sees the inner \( as literal text
# inside math mode and fails to parse it — the reported "\frac..." shown
# as raw red error text). Japanese text and already-fine plain expressions
# (e.g. "6x - 7 = -31", which has no LaTeX commands) are left untouched.
_MATH_SAFE_RUN = re.compile(r"[A-Za-z0-9\\^_{}()\[\]$.,+\-*/=' \t]+")
_LATEX_TRIGGER = re.compile(r"\\[A-Za-z]|[A-Za-z0-9)\]][\^_]")
# Checked in this order so "$$...$$" isn't mistaken for a lone "$...$".
_ALREADY_DELIMITED = (('$$', '$$'), (r'\[', r'\]'), (r'\(', r'\)'), ('$', '$'))


def _is_already_delimited(stripped):
    return any(
        stripped.startswith(left) and stripped.endswith(right)
        and len(stripped) >= len(left) + len(right)
        for left, right in _ALREADY_DELIMITED
    )


def _wrap_latex_runs(text):
    def replace(match):
        run = match.group(0)
        stripped = run.strip()
        if not stripped:
            return run
        if _is_already_delimited(stripped):
            return run  # KaTeX's own configured delimiters already cover this
        if not _LATEX_TRIGGER.search(stripped):
            return run  # plain text/arithmetic with no actual LaTeX syntax — leave as-is
        leading_ws = run[:len(run) - len(run.lstrip())]
        trailing_ws = run[len(run.rstrip()):]
        return f'{leading_ws}\\({stripped}\\){trailing_ws}'

    return _MATH_SAFE_RUN.sub(replace, text)


@register.filter
def latexify(value):
    """Wrap embedded LaTeX in \\( \\) for KaTeX auto-render, then escape
    the whole string ourselves and mark it safe — never a blanket
    autoescape-off, so anything the model generates outside of a math run
    still can't inject HTML."""
    if value is None:
        return ''
    return mark_safe(escape(_wrap_latex_runs(str(value))))
