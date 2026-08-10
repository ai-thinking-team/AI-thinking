from django import forms


class OtherSubjectAttemptForm(forms.Form):
    answer = forms.CharField(widget=forms.Textarea)
    reasoning_and_evidence = forms.CharField(widget=forms.Textarea)
    confidence = forms.TypedChoiceField(coerce=int, choices=[(value, value) for value in range(1, 6)])
