import base64
import os

import anthropic

from .exceptions import AIServiceUnavailable, InvalidAIResponse

CLAUDE_MODEL = 'claude-opus-5'


def generate_ai_response(
    *, system_prompt, user_prompt, response_schema=None, file_bytes=None, mime_type=None
):
    """Return validated AI output behind one provider-neutral boundary.

    Set `file_bytes`/`mime_type` to attach an uploaded file (image, PDF, ...)
    alongside the prompt.
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise AIServiceUnavailable(
            'AI support is unavailable. Continue with the curated diagnostic and hint ladder.'
        )

    content = []
    if file_bytes is not None:
        encoded = base64.b64encode(file_bytes).decode('ascii')
        if mime_type and mime_type.startswith('image/'):
            content.append({
                'type': 'image',
                'source': {'type': 'base64', 'media_type': mime_type, 'data': encoded},
            })
        elif mime_type == 'application/pdf':
            content.append({
                'type': 'document',
                'source': {'type': 'base64', 'media_type': 'application/pdf', 'data': encoded},
            })
        else:
            try:
                content.append({'type': 'text', 'text': file_bytes.decode('utf-8')})
            except UnicodeDecodeError:
                content.append({'type': 'text', 'text': '[添付ファイルの内容を読み取れませんでした]'})
    content.append({'type': 'text', 'text': user_prompt})

    client = anthropic.Anthropic(api_key=api_key)
    kwargs = {}
    if response_schema is not None:
        kwargs['output_config'] = {'format': {'type': 'json_schema', 'schema': response_schema}}

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8192,
            system=system_prompt,
            messages=[{'role': 'user', 'content': content}],
            **kwargs,
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        raise AIServiceUnavailable(f'AI provider returned an error: {exc}') from exc

    if response.stop_reason == 'refusal':
        raise AIServiceUnavailable('AI declined to respond to this request.')

    try:
        return next(block.text for block in response.content if block.type == 'text')
    except StopIteration as exc:
        raise InvalidAIResponse('AI provider returned an unexpected response shape.') from exc
