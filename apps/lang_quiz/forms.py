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
    answer = forms.CharField(widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'あなたの回答を入力してください'}), label='回答')
    reasoning = forms.CharField(widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'この回答に至った理由や考え方を説明してください'}), label='理由・考え方')
    confidence = forms.TypedChoiceField(
        coerce=int,
        choices=[(value, f'{value} - ' + ('全く自信がない' if value == 1 else '非常に自信がある' if value == 5 else f'レベル{value}')) for value in range(1, 6)],
        label='自信度 (1~5)'
    )


class TeachBackForm(forms.Form):
    response = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': '自分の言葉で学んだ概念や解き方を説明してください...'}),
        label='学んだ概念の説明 (Teach-Back)'
    )


class TransferAttemptForm(forms.Form):
    answer = forms.CharField(widget=forms.Textarea(attrs={'rows': 2, 'placeholder': '応用問題の回答を入力してください'}), label='回答')
    reasoning = forms.CharField(widget=forms.Textarea(attrs={'rows': 3, 'placeholder': '考え方の理由を説明してください'}), label='理由・考え方')
    confidence = forms.TypedChoiceField(
        coerce=int,
        choices=[(value, f'{value} - ' + ('全く自信がない' if value == 1 else '非常に自信がある' if value == 5 else f'レベル{value}')) for value in range(1, 6)],
        label='自信度 (1~5)'
    )


class FileUploadForm(forms.Form):
    file = forms.FileField(
        label='問題作成用ファイルのアップロード (.txt, .md, .json, .csv, .pdf)',
        widget=forms.ClearableFileInput(attrs={'accept': '.txt,.md,.json,.csv,.pdf'}),
    )


class MaterialQuizForm(forms.Form):
    files = MultipleFileField(
        label='教材ファイル（複数選択可）',
        required=False,
        widget=MultipleFileInput(attrs={
            'accept': '.txt,.md,.csv,.json,.pdf',
            'class': 'file-input',
        }),
    )
    instruction = forms.CharField(
        label='どのような問題を作ってほしいですか？',
        max_length=1000,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': '例：ベトナム語の単語の意味を、日本語で答える問題にしてください。',
        }),
    )

    def clean_files(self):
        files = [item for item in self.cleaned_data.get('files', []) if item]
        if not files:
            raise forms.ValidationError('教材ファイルまたはフォルダを選択してください。')
        return files


class QuizAnswerForm(forms.Form):
    answer = forms.CharField(
        label='回答',
        max_length=500,
        widget=forms.TextInput(attrs={
            'autocomplete': 'off',
            'placeholder': '答えを入力',
            'autofocus': True,
        }),
    )
