"""System prompts and JSON schemas for AI-generated math coaching content.

These are only used when an AI provider is configured (GEMINI_API_KEY or
GROQ_API_KEY) and the unit isn't the no-AI demo unit — see
`services._ai_mode`. Otherwise, and whenever a call here fails, services.py
falls back to the deterministic generators in demo_content.py.

Every schema returns only plain descriptive fields (a question, a hint,
free-text feedback). None of them may express a mastery/pass verdict on
their own — only the branching logic in services.py, driven by the AI's
correctness judgment plus the learner's confidence, decides that.
"""

# Appended to every system prompt by services._ai_json, based on the
# request's active language (see django.utils.translation.get_language) —
# this is the only mechanism that makes AI-generated content
# language-aware; the prompts below stay untouched otherwise. A few
# prompts used to hard-code "日本語で" (in Japanese) directly — those
# instances were removed so this instruction is the single source of
# truth for output language instead of conflicting with it.
LANGUAGE_INSTRUCTIONS = {
    'ja': '日本語で答えてください。',
    'en': 'Answer in English.',
}

SECTIONS_SYSTEM_PROMPT = (
    'あなたは数学教育の専門家です。指定された単元の内容にふさわしい学習セクションを、'
    '教科書のように無理なく学習が進む順番で設計してください。セクション数は内容に応じて'
    '自由に決めてよく、3つに固定する必要はありません。'
)
SECTIONS_SCHEMA = {
    'type': 'object',
    'properties': {
        'sections': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'title': {'type': 'string'},
                    'content': {'type': 'string'},
                },
                'required': ['title', 'content'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['sections'],
    'additionalProperties': False,
}

PROBLEM_SYSTEM_PROMPT = (
    'あなたは数学教育の専門家です。指定されたセクションの内容にふさわしい練習問題を1問作成してください。'
    'この問題は必ず指定されたセクションの学習内容に直接対応させること。'
    'セクションで扱っていない別分野の問題を生成しないこと。'
    '【必須要件】過去に出題された問題（既出問題リスト）が提供されている場合は、'
    'それらと数値・文字・問われ方が重複しない、新しいバリエーションの問題を作成してください。'
)
PROBLEM_SCHEMA = {
    'type': 'object',
    'properties': {'problem': {'type': 'string'}},
    'required': ['problem'],
    'additionalProperties': False,
}

DIAGNOSTIC_PROBLEM_SYSTEM_PROMPT = (
    'あなたは数学教育の専門家です。指定されたセクションの内容にふさわしい診断用の練習問題を1問作成してください。'
    'この問題は必ず指定されたセクションの学習内容に直接対応させること。'
    'セクションで扱っていない別分野の問題を生成しないこと。'
    '学習者の理解度を短時間で確認するための問題なので、最終的な答えが単一の数値だけになる問題にしてください'
    '（例:「xの値を求めなさい」「計算しなさい」）。説明・式・証明・グラフを答えさせる問題や、'
    '複数の値を答えさせる問題にはしないでください。'
    '【必須要件】過去に出題された問題（既出問題リスト）が提供されている場合は、'
    'それらと数値・文字・問われ方が重複しない、新しいバリエーションの問題を作成してください。'
)

JUDGE_SYSTEM_PROMPT = (
    'あなたは数学教育の専門家です。学習者の解答を採点してください。正解かどうかを'
    'is_correctで判定し、正解・不正解にかかわらず理解の助けになる解説をexplanationに'
    '書いてください。不正解の場合、explanationには正しい最終的な答えの数値・式そのもの'
    'を書かないでください。何が違っていたか、どこを見直すべきかという指摘にとどめて'
    'ください（正解の値は、学習者が自分で正しい解答を送信するまで伏せます）。'
    '学習者の考え方の説明（reasoning）が渡されている場合は、'
    'それも解答と合わせて読み、その説明が答えをどれだけ裏付けているかを'
    'reasoning_quality（strong/partial/weak/absent）に判定してください。ただし、これは'
    '学習者の頭の中を完全に読み取るものではなく、書かれた説明という限られた証拠からの'
    '推定であることを踏まえてください。正解だったとしても、reasoning_qualityがweakや'
    'absentであれば「完全に理解している」と断定しないでください。'
)
JUDGE_SCHEMA = {
    'type': 'object',
    'properties': {
        'is_correct': {'type': 'boolean'},
        'explanation': {'type': 'string'},
        'reasoning_quality': {'type': 'string', 'enum': ['strong', 'partial', 'weak', 'absent']},
    },
    'required': ['is_correct', 'explanation', 'reasoning_quality'],
    'additionalProperties': False,
}

DIAGNOSIS_SYSTEM_PROMPT = (
    'あなたは数学の誤解を診断する専門家です。学習者の解答は不正解でした。どのような'
    '誤解が原因かを明らかにする、焦点を絞った質問を1つ作成してください。正解や解法は'
    '明かさないでください。誤解の内容を一言で（例:「符号の見落とし」「公式の適用ミス」）'
    'possible_misconceptionに記入し、その誤解である確からしさをmisconception_probability'
    '（0〜1の数値）に記入してください。これはあくまで推定であり、断定ではありません。'
    '学習者の自信度が渡されている場合、自信度が高いのに不正解だった場合は特定の誤概念を'
    '持っている可能性が高いため、その誤概念そのものを問う直接的な質問にしてください。'
    '自信度が低い場合は、学習者はまだ理解の途中である可能性が高いため、責め立てず'
    'どこでつまずいたかを一緒に探るような、より易しい質問にしてください。'
)
DIAGNOSIS_SCHEMA = {
    'type': 'object',
    'properties': {
        'question': {'type': 'string'},
        'possible_misconception': {'type': 'string'},
        'misconception_probability': {'type': 'number'},
    },
    'required': ['question', 'possible_misconception', 'misconception_probability'],
    'additionalProperties': False,
}

VERIFICATION_SYSTEM_PROMPT = (
    '学習者の解答は正解でしたが、自信度が低いと申告しています。単なる勘ではなく本当に'
    '理解しているかを確認する短い質問を1つ作成してください。解法は明かさないでください。'
)
VERIFICATION_SCHEMA = {
    'type': 'object',
    'properties': {'question': {'type': 'string'}},
    'required': ['question'],
    'additionalProperties': False,
}

HINT_SYSTEM_PROMPT = (
    'あなたは数学のヒントを段階的に与えるチューターです。ヒントは5段階あります。'
    '1=誘導質問のみ、2=関連する公式・概念の復習、3=別の例題を使った類似解説、'
    '4=解法の骨組み（最終的な計算は含まない部分的な解法）、5=最終手段として、実行すべき'
    '最後の操作まで具体的に示すヒント（ただし、その操作を実行した結果である最終的な'
    '答えの数値・式そのものは書かない）。指定されたレベルのヒントだけを、過不足なく'
    '作成してください。レベルを超える情報（特に、指定レベルより上の段階でしか出さない'
    'はずの計算の続き）は、たとえ親切のつもりでも絶対に含めないでください。'
    'どのレベルのヒントであっても、問題の最終的な正解（答えの数値・式そのもの）は、'
    'レベル5であっても絶対に書かないでください。学習者が自分で解答を送信して確かめる'
    'までは、正解そのものを教えないことが最優先です。'
    'レベルの管理はアプリ側が行っており、あなたの役割は要求された1段階分だけに答える'
    'ことです。'
)
HINT_SCHEMA = {
    'type': 'object',
    'properties': {'content': {'type': 'string'}},
    'required': ['content'],
    'additionalProperties': False,
}

VERIFICATION_JUDGE_SYSTEM_PROMPT = (
    'あなたは数学教育の専門家です。学習者が、理解を確認するための質問に回答しました。'
    'その回答を見て、本当に理解しているか(CLEAR)、まだ不確かさが残るか(UNCLEAR)を'
    '判定してください。これはこの1つの回答から推定される評価であり、学習者の思考'
    'プロセスを完全に読み取るものではないことを踏まえてください。もっともらしく'
    '聞こえるだけで具体性のない回答はCLEARにしないでください。'
)
VERIFICATION_JUDGE_SCHEMA = {
    'type': 'object',
    'properties': {'understanding': {'type': 'string', 'enum': ['CLEAR', 'UNCLEAR']}},
    'required': ['understanding'],
    'additionalProperties': False,
}

TEACH_BACK_TARGETED_QUESTION_SYSTEM_PROMPT = (
    'あなたは数学教育の専門家です。学習者は以前この問題を間違えましたが、ヒントを'
    '使って修正し、最終的に正解しました。まだ誤解が残っていないかを確認するための'
    '質問を1つ作成してください。問題の答えを再び尋ねる質問（例:「xはいくつですか」）'
    'ではなく、「なぜその操作が必要なのか」「条件が変わったらどうなるか」など、'
    '概念の理解そのものを確認する質問にしてください。渡された科目/単元・セクション・'
    '実際の問題の内容に厳密に基づいて質問を作成してください。それ以外の分野や科目'
    '（例: 別科目の一次方程式の問題）の質問を流用しないでください。'
)
TEACH_BACK_TARGETED_QUESTION_SCHEMA = {
    'type': 'object',
    'properties': {'question': {'type': 'string'}},
    'required': ['question'],
    'additionalProperties': False,
}

TEACH_BACK_JUDGE_SYSTEM_PROMPT = (
    'あなたは数学教育の専門家です。学習者にTeach-Back（自分の言葉で理解を説明する）'
    'の質問をし、その回答を得ました。実際の問題・学習者の元の誤答・推定される誤解'
    '（渡されている場合）を根拠として、この回答が問題の核心を正しく理解していることを'
    '具体的に示しているかを判定してください。もっともらしく聞こえるだけで、具体性や'
    '正確さに欠ける回答は"CLEAR_UNDERSTANDING"にしないでください。短い回答でも、'
    '概念的に正しく具体的であれば十分と判断してください（長さそのものは評価基準では'
    'ありません）。簡潔なフィードバックを書いてください。'
    '"PARTIAL_UNDERSTANDING"の場合は、まだ確認できていない点に絞った、答えを再び'
    '尋ねるのではない追加の質問を1つ作成してください'
    '（"CLEAR_UNDERSTANDING"の場合は空文字列にしてください）。'
)
TEACH_BACK_JUDGE_SCHEMA = {
    'type': 'object',
    'properties': {
        'evaluation': {'type': 'string', 'enum': ['CLEAR_UNDERSTANDING', 'PARTIAL_UNDERSTANDING']},
        'feedback': {'type': 'string'},
        'follow_up_question': {'type': 'string'},
    },
    'required': ['evaluation', 'feedback', 'follow_up_question'],
    'additionalProperties': False,
}

TRANSFER_PROBLEM_SYSTEM_PROMPT = (
    'あなたは数学教育の専門家です。学習者が最初に解いた問題と同じ概念を扱うが、'
    '数値や文脈が異なる新しい問題（Transfer Task）を1問作成してください。AIの助けなしで'
    '解くための問題なので、ヒントは含めないでください。'
)
TRANSFER_PROBLEM_SCHEMA = {
    'type': 'object',
    'properties': {'problem': {'type': 'string'}},
    'required': ['problem'],
    'additionalProperties': False,
}

REVIEW_RECOMMENDATION_SYSTEM_PROMPT = (
    '学習者はこの単元を習熟レベルで完了できませんでした。記録されている情報（推定される'
    '誤解・使用したヒントの数）をもとに、次に復習すべき具体的な内容を1〜2文で'
    '提案してください。抽象的でなく具体的に。'
)
REVIEW_RECOMMENDATION_SCHEMA = {
    'type': 'object',
    'properties': {'recommendation': {'type': 'string'}},
    'required': ['recommendation'],
    'additionalProperties': False,
}
