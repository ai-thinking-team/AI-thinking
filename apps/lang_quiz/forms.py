from django import forms


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        clean_one = super().clean
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            return [clean_one(item, initial) for item in data]
        return [clean_one(data, initial)]


class LanguageAttemptForm(forms.Form):
    answer = forms.CharField(widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Enter your answer here'}), label='Answer')
    reasoning = forms.CharField(widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Explain your thinking and how you arrived at this answer'}), label='Reasoning')
    confidence = forms.TypedChoiceField(
        coerce=int,
        choices=[(value, f'{value} - ' + ('Not confident at all' if value == 1 else 'Very confident' if value == 5 else f'Level {value}')) for value in range(1, 6)],
        label='Confidence (1–5)'
    )


class TeachBackForm(forms.Form):
    response = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'Explain the concept or solution in your own words...'}),
        label='Explanation in your own words (Teach-Back)'
    )


class TransferAttemptForm(forms.Form):
    answer = forms.CharField(widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Enter your answer to the transfer question'}), label='Answer')
    reasoning = forms.CharField(widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Explain your reasoning'}), label='Reasoning')
    confidence = forms.TypedChoiceField(
        coerce=int,
        choices=[(value, f'{value} - ' + ('Not confident at all' if value == 1 else 'Very confident' if value == 5 else f'Level {value}')) for value in range(1, 6)],
        label='Confidence (1–5)'
    )


class FileUploadForm(forms.Form):
    file = forms.FileField(
        label='Upload file for question generation (.txt, .md, .json, .csv, .pdf)',
        widget=forms.ClearableFileInput(attrs={'accept': '.txt,.md,.json,.csv,.pdf'}),
    )


class MaterialQuizForm(forms.Form):
    answer_mode = forms.ChoiceField(
        label='Vocabulary answer format',
        choices=(
            ('multiple_choice', '5-choice'),
            ('typing', 'Typing'),
        ),
        initial='multiple_choice',
        required=False,
        widget=forms.RadioSelect,
    )
    files = MultipleFileField(
        label='Material files (multiple allowed)',
        required=False,
        widget=MultipleFileInput(attrs={
            'accept': '.txt,.md,.csv,.json,.pdf',
            'class': 'file-input',
        }),
    )
    instruction = forms.CharField(
        label='What kind of questions would you like?',
        max_length=1000,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'e.g. Create reading comprehension questions based on the main ideas in this passage.',
        }),
    )

    def clean_files(self):
        files = [item for item in self.cleaned_data.get('files', []) if item]
        if not files:
            raise forms.ValidationError('Please select at least one material file or folder.')
        return files


class QuizAnswerForm(forms.Form):
    def __init__(self, *args, question=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = question.get('choices', []) if question else []
        if choices:
            self.fields['answer'] = forms.ChoiceField(
                label='Choose one answer',
                choices=[(choice, choice) for choice in choices],
                widget=forms.RadioSelect,
            )
        else:
            self.fields['answer'] = forms.CharField(
                label='Answer',
                max_length=500,
                widget=forms.TextInput(attrs={
                    'autocomplete': 'off',
                    'placeholder': 'Type your answer',
                    'autofocus': True,
                }),
            )
