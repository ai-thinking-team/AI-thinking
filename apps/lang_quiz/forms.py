from django import forms


class LanguageAttemptForm(forms.Form):
    answer = forms.CharField(widget=forms.Textarea)
    reasoning = forms.CharField(widget=forms.Textarea)
    confidence = forms.TypedChoiceField(coerce=int, choices=[(value, value) for value in range(1, 6)])
