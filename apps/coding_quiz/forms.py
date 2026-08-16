from django import forms


class AccessibleForm(forms.Form):
    """Associate server-side validation feedback with each rendered control."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.error_messages['required'] = 'This field is required.'
        if not self.is_bound:
            return
        for name in self.fields:
            bound_field = self[name]
            if bound_field.errors:
                bound_field.field.widget.attrs.update({
                    'aria-invalid': 'true',
                    'aria-describedby': f'{bound_field.auto_id}_error',
                })


class CodingPlanForm(AccessibleForm):
    solution_plan = forms.CharField(
        label='Describe your solution plan before writing code',
        widget=forms.Textarea(attrs={'rows': 4}),
    )
    predicted_output = forms.CharField(
        label='Predict the output for the public example',
        widget=forms.Textarea(attrs={'rows': 3}),
    )


class CodingAttemptForm(AccessibleForm):
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


class DiagnosisForm(AccessibleForm):
    diagnosis_answer = forms.CharField(
        label='Your answer',
        widget=forms.Textarea(attrs={'rows': 4}),
    )


class RevisionForm(CodingAttemptForm):
    pass


class TeachBackForm(AccessibleForm):
    original_issue = forms.CharField(
        label='What was wrong or uncertain in your first attempt?',
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    failure_reason = forms.CharField(
        label='Why did the original approach work or fail?',
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    correction = forms.CharField(
        label='What did you change, or what made the original solution correct?',
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    concept = forms.CharField(
        label='What programming concept did you learn?',
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    prevention = forms.CharField(
        label='How will you avoid a similar mistake next time?',
        widget=forms.Textarea(attrs={'rows': 3}),
    )


class TransferAttemptForm(CodingAttemptForm):
    pass
