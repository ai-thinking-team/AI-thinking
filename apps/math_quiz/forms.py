from django import forms


class MathAttemptForm(forms.Form):
    answer = forms.CharField()
    reasoning_steps = forms.CharField(widget=forms.Textarea)
    confidence = forms.TypedChoiceField(coerce=int, choices=[(value, value) for value in range(1, 6)])
