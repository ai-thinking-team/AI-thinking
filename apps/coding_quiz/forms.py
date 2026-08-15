from django import forms


class CodingAttemptForm(forms.Form):
    source_code = forms.CharField(
        label='Python source code',
        widget=forms.Textarea(attrs={'rows': 12, 'spellcheck': 'false'}),
    )
    reasoning = forms.CharField(
        label='Explain your plan and reasoning',
        widget=forms.Textarea(attrs={'rows': 5}),
    )
    confidence = forms.TypedChoiceField(
        coerce=int,
        choices=[
            (1, '1 — I am guessing'),
            (2, '2 — I am not sure'),
            (3, '3 — I understand part of it'),
            (4, '4 — I am fairly confident'),
            (5, '5 — I can explain my solution'),
        ],
    )


class TeachBackForm(forms.Form):
    explanation = forms.CharField(widget=forms.Textarea(attrs={'rows': 6}))


class TransferAttemptForm(CodingAttemptForm):
    pass
