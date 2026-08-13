"""Generates locale/{ja,en}/LC_MESSAGES/django.po from a single source
dict, so every msgid is written exactly once and consistently for both
locales. ja's msgstr is identical to msgid (the source strings already
are Japanese); en's msgstr is the English translation. Run once, by hand,
during development — not part of the Django app itself.
"""
import os

# msgid -> English translation. Order roughly follows the order strings
# were introduced across templates then Python modules.
TRANSLATIONS = {
    # --- templates: plain {% trans %} ---
    '1 = 勘 ・ 3 = 部分的に理解 ・ 5 = 説明できる': '1 = Guess, 3 = Partial understanding, 5 = Can explain',
    '1〜2文でOKです': '1-2 sentences is fine',
    'AIのヒントなしで解いてください。': 'Solve this without AI hints.',
    'Complete! 🎉': 'Complete! 🎉',
    '「追加」を押すと、セクションが自動生成されます。': 'Sections will be generated automatically when you press "Add".',
    'おすすめのセクション': 'Recommended sections',
    'ここにファイルをドラッグ&ドロップ': 'Drag & drop files here',
    'ここに回答を入力してください': 'Enter your answer here',
    'ここに解答を入力してください': 'Enter your answer here',
    'このコースはComplete!です 🎉': 'This course is Complete! 🎉',
    'この科目に入る前に、いくつかの問題を解いて今の理解度を確認しましょう。':
        "Before starting this subject, let's check your current understanding with a few questions.",
    'この科目を削除しますか？': 'Delete this subject?',
    'この科目を追加': 'Add this subject',
    'どう考えて修正したか説明してください': 'Explain how you thought about the correction',
    'どう考えて解いたか説明してください': 'Explain how you thought about solving it',
    'もう少し練習するとよさそうな点': 'Areas that could use more practice',
    'サンプル': 'Sample',
    'セクションがまだありません。': 'There are no sections yet.',
    'セクション一覧へ進む': 'Go to section list',
    'ホームに戻る': 'Back to home',
    'メニュー': 'Menu',
    '不正解': 'Incorrect',
    '不正解でした。誤解を明らかにするための質問です。': "That was incorrect. Here's a question to help identify the misunderstanding.",
    '例: x = 4': 'e.g. x = 4',
    '例: 二次関数、微分の基礎': 'e.g. Quadratic functions, Basics of differentiation',
    '再提出': 'Resubmit',
    '削除': 'Delete',
    '参考ファイルをダウンロード': 'Download reference file',
    '参考ファイル（任意・複数可）': 'Reference files (optional, multiple allowed)',
    '資料': 'Materials',
    '資料を追加': 'Add material',
    '追加': 'Add',
    '資料はまだありません。': 'No materials yet.',
    '各単元で「要復習」になったセクションを集めました。解きなおすと、そのセクションは新しい問題から再スタートします。':
        'Sections marked "Needs Review" from each unit are collected here. '
        'Retrying a section starts it over with a new question.',
    '回答して次へ': 'Answer and continue',
    '回答する': 'Answer',
    '学習の記録': 'Learning record',
    '復習して、もう一度解きなおそう。': 'Review and try again.',
    '提出': 'Submit',
    '数学': 'Math',
    '新しい科目を追加': 'Add a new subject',
    '最初からやり直す': 'Start over',
    '最初の解答': 'First attempt',
    '最後に、今回の考え方を自分の言葉で確認してみましょう。長い説明は必要ありません（目安10〜20秒、1〜2文でOKです）。':
        "Finally, let's check your thinking in your own words. "
        "A long explanation isn't necessary (about 10-20 seconds, 1-2 sentences is fine).",
    '未選択でも追加できます': 'You can add it even without selecting a file',
    '次のおすすめ:': 'Next recommendation:',
    '正解': 'Correct',
    '正解でした！自信度が低かったので、理解を確認します。': "That was correct! Since your confidence was low, let's check your understanding.",
    '理解の証拠': 'Evidence of understanding',
    '理解度の自己評価と結果に少しズレがあります。次は自信度も意識して答えてみましょう。':
        "There's a slight mismatch between your self-assessed understanding and the result. "
        'Try being mindful of your confidence next time.',
    '科目': 'Subject',
    '科目を選んで診断からTransfer Checkまで進めましょう。学び終えた分だけ、コースの達成率が積み上がります。':
        'Choose a subject and work from the diagnostic through to the Transfer Check. '
        'Your course completion rate builds up as you learn.',
    '科目名': 'Subject name',
    '科目名を入力し、参考資料があればドラッグ&ドロップしてください。セクション構成は自動で作成されます。':
        'Enter a subject name, and drag & drop reference material if you have any. '
        'The section structure will be created automatically.',
    '考え方': 'Reasoning',
    '考え方の説明': 'Explanation of your reasoning',
    '自信度': 'Confidence',
    '解きなおす': 'Try again',
    '解答': 'Answer',
    '解答（修正版）': 'Answer (revised)',
    '診断クイズ': 'Diagnostic quiz',
    '診断結果': 'Diagnostic result',
    '達成率': 'Completion rate',
    '選択中': 'Selected',
    '間違えた問題': 'Mistakes',
    '間違えた問題はまだありません。学習を進めると、要復習になった問題がここに表示されます。':
        'No mistakes yet. As you learn, problems marked Needs Review will appear here.',
    '（またはクリックして選択、複数選択可）': '(or click to select, multiple files allowed)',
    '（最終手段）': '(last resort)',

    # --- templates: {% blocktrans %} (literal % doubled to %%, matching
    # BlockTranslateNode.render_token_list's own escaping) ---
    '達成率 %(percent)s%%（%(mastered)s/%(total)s）': 'Completion rate %(percent)s%% (%(mastered)s/%(total)s)',
    'セクション %(n)s': 'Section %(n)s',
    '推定される誤解: %(misconception)s': 'Estimated misconception: %(misconception)s',
    'コース達成率 %(course_percent)s%%': 'Course completion %(course_percent)s%%',
    'ヒント レベル%(level)s': 'Hint level %(level)s',
    'これまでのヒントを見る（%(count_hints)s件）': 'View previous hints (%(count_hints)s)',
    'レベル%(level)s:': 'Level %(level)s:',
    '今回つまずいたポイント: %(point)s': 'What tripped you up this time: %(point)s',
    '修正 %(n)s': 'Revision %(n)s',
    '使用したヒント（%(count_hints)s件）': 'Hints used (%(count_hints)s)',
    '問題 %(current)s / %(total)s': 'Question %(current)s / %(total)s',
    '%(total)s 問正解': '%(total)s correct',
    '%(total)sセクション': '%(total)s sections',

    # --- views.py ---
    '「%(name)s」はすでに登録されています。': '"%(name)s" is already registered.',
    'この学習セッションをリセットしました。': 'This learning session has been reset.',
    'サンプル科目は削除できません。': 'The sample subject cannot be deleted.',
    '不明な操作です。': 'Unknown action.',
    '不正なリクエストです。': 'Invalid request.',
    'ファイルを選択してください。': 'Please select a file.',
    '資料を追加しました。': 'Material added.',
    '修正': 'Revision',
    '完了': 'Done',
    '新しい問題から、この学習セッションを始めます。': 'Starting this learning session over with a new question.',
    '次のヒントを確認してみましょう。': 'Take a look at the next hint.',
    '理解が確認できました。': 'Your understanding has been confirmed.',
    '確認': 'Verification',
    '確認質問への回答を保存しました。': 'Your answer to the verification question has been saved.',
    '科目名を入力してください。': 'Please enter a subject name.',
    '診断': 'Diagnosis',
    '診断クイズがまだ完了していません。': 'The diagnostic quiz is not yet complete.',
    '診断質問への回答を保存しました。': 'Your answer to the diagnostic question has been saved.',

    # --- mastery.py ---
    'Mastered': 'Mastered',
    '再確認の時期です': 'Time for a recheck',
    '未着手': 'Not started',
    '理解途中': 'In progress',
    '自信不足かもしれません': 'May be underconfident',
    '自信過剰かもしれません': 'May be overconfident',
    '要復習': 'Needs review',

    # --- demo_content.py (NEXT_STEP_LABELS) ---
    'AIの助けなしで解く応用問題（Transfer Check）に進みます。': "Moving on to an application problem (Transfer Check) you'll solve without AI help.",
    'この単元は習得（Mastered）と判定されました。': 'This unit has been marked as Mastered.',
    'ヒントを見ながら解答を修正します。': 'Revise your answer using the hints.',
    '不正解だったので、誤解を診断する質問に進みます。': "That was incorrect, so let's move to a question that diagnoses the misunderstanding.",
    '復習が必要です。': 'This needs review.',
    '正解でしたが自信度が低いので、理解を確認する質問に進みます。':
        "That was correct, but since your confidence was low, let's move to a question to check your understanding.",
    '自分の言葉で説明するTeach-Backに進みます。': 'Moving on to Teach-Back, where you explain it in your own words.',

    # --- services.py (ValidationError messages) ---
    'Teach-Backの回答を入力してください。': 'Please enter your Teach-Back answer.',
    'Teach-Backの質問が見つかりません。': 'The Teach-Back question could not be found.',
    'Teach-Backはこのステップでは利用できません。': 'Teach-Back is not available at this step.',
    'Transfer Checkはこのステップでは利用できません。': 'Transfer Check is not available at this step.',
    'Transfer Checkはすでに提出済みです。': 'The Transfer Check has already been submitted.',
    'この問題はすでに回答済みか、存在しません。': 'This question has already been answered, or does not exist.',
    'この診断クイズはすでに完了しています。': 'This diagnostic quiz has already been completed.',
    '修正の提出はこのステップでは利用できません。': 'Submitting a revision is not available at this step.',
    '回答を入力してください。': 'Please enter an answer.',
    '最初の解答はこのステップでは提出できません。': 'The first attempt cannot be submitted at this step.',
    '最初の解答はすでに提出済みです。': 'The first attempt has already been submitted.',
    '確認質問に回答してから進んでください。': 'Please answer the verification question before continuing.',
    '確認質問はこのステップでは利用できません。': 'The verification question is not available at this step.',
    '自信度を選択してください。': 'Please select a confidence level.',
    '解答と考え方の説明の両方を入力してください。': 'Please enter both your answer and an explanation of your reasoning.',
    '診断質問に回答してから進んでください。': 'Please answer the diagnostic question before continuing.',
    '診断質問はこのステップでは利用できません。': 'The diagnostic question is not available at this step.',
}


def escape(text):
    return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def write_po(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(
            'msgid ""\n'
            'msgstr ""\n'
            '"Content-Type: text/plain; charset=UTF-8\\n"\n'
            '"Content-Transfer-Encoding: 8bit\\n"\n\n'
        )
        for msgid, msgstr in entries.items():
            f.write(f'msgid "{escape(msgid)}"\n')
            f.write(f'msgstr "{escape(msgstr)}"\n\n')


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    write_po(
        os.path.join(base, 'locale', 'en', 'LC_MESSAGES', 'django.po'),
        TRANSLATIONS,
    )
    write_po(
        os.path.join(base, 'locale', 'ja', 'LC_MESSAGES', 'django.po'),
        {msgid: msgid for msgid in TRANSLATIONS},
    )
    print(f'{len(TRANSLATIONS)} entries written for each locale.')


if __name__ == '__main__':
    main()
