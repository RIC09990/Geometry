from typing import Literal

import pytest
from pydantic import BaseModel, Field

from server.chat_context import prepare_chat_messages


class Message(BaseModel):
    role: Literal['user', 'assistant']
    content: str
    images: list[dict[str, str]] = Field(default_factory=list)


def user(content, *image_names):
    return Message(role='user', content=content,
                   images=[{'name': name, 'dataUrl': 'data:' + name} for name in image_names])


def assistant(content):
    return Message(role='assistant', content=content)


def pairs(count, offset=0):
    return [message for index in range(count)
            for message in (user(f'question {index + offset}'), assistant(f'answer {index + offset}'))]


def test_the_whole_conversation_is_sent():
    messages = [*pairs(14), user('current')]
    assert prepare_chat_messages(messages) == messages


def test_a_very_long_current_turn_keeps_the_history_before_it():
    latest = user('current attachment text ' * 4000, 'page 1', 'page 2')
    messages = [user('old'), assistant('old answer'), latest]
    assert prepare_chat_messages(messages) == messages
    assert len(messages[-1].content) > 24000


def test_unicode_content_is_preserved_in_full():
    messages = [user('😀' * 12000), assistant('角' * 12000), user('?')]
    assert prepare_chat_messages(messages) == messages


def test_uploads_of_every_retained_turn_travel_with_the_request():
    first = user('first question', 'old page')
    second = user('second question', 'new page 1')
    third = user('third question', 'new page 2', 'new page 3')
    messages = [first, assistant('first answer'), second, assistant('second answer'), third]
    before = [message.model_dump() for message in messages]
    result = prepare_chat_messages(messages)
    assert [image['name'] for image in result[0].images] == ['old page']
    assert result[0] is first
    assert [image['name'] for image in result[2].images] == ['new page 1']
    assert result[2] is second
    assert [image['name'] for image in result[4].images] == ['new page 2', 'new page 3']
    assert [message.model_dump() for message in messages] == before


def test_old_uploads_stay_in_context_until_compaction_summarizes_them():
    messages = [user('old upload', 'old page'), assistant('old answer'), *pairs(13), user('explain')]
    result = prepare_chat_messages(messages)
    assert result == messages
    assert result[0].images == messages[0].images


def test_assistant_groups_are_never_split():
    group = lambda index: [user(f'question {index}'), *(assistant(f'fragment {index}-{fragment}') for fragment in range(6))]
    messages = [*group(0), *group(1), *group(2), *group(3), user('current')]
    assert prepare_chat_messages(messages) == messages


def test_orphan_assistant_prefix_is_dropped_but_cancelled_user_turns_survive():
    messages = [assistant('orphan answer'), user('upload', 'worksheet'),
                user('extra detail'), assistant('response'), user('follow-up')]
    result = prepare_chat_messages(messages)
    assert result == messages[1:]
    assert result[0].images == messages[1].images


@pytest.mark.parametrize('latest', ['换一道题', 'Here is a new problem', 'Check my answer', '继续解释'])
def test_content_is_not_rewritten_or_used_to_guess_a_topic_switch(latest):
    messages = [user('original question'), assistant('original answer'), user(latest)]
    assert prepare_chat_messages(messages) == messages


@pytest.mark.parametrize('messages', [[], [assistant('unfinished answer')]])
def test_invalid_request_end_is_rejected(messages):
    with pytest.raises(ValueError, match='user message'):
        prepare_chat_messages(messages)


def test_a_long_conversation_of_short_turns_is_accepted():
    from server.ai import ChatRequest, prepared_chat
    messages = [{'role': 'user' if index % 2 == 0 else 'assistant', 'content': f'message {index}'}
                for index in range(61)]
    assert len(prepared_chat(ChatRequest(messages=messages)).messages) == 61


def test_actual_message_model_removes_response_metadata_before_context_selection():
    from server.ai import Message as ApiMessage
    answer = ApiMessage.model_validate({'role': 'assistant', 'content': 'Previous solution',
                                       'grading': {'score': 0}, 'reportPdf': {'dataUrl': 'ignored'},
                                       'sources': [{'title': 'ignored'}], 'model': 'old-model'})
    messages = [ApiMessage(role='user', content='question'), answer,
                ApiMessage(role='user', content='follow-up')]
    result = prepare_chat_messages(messages)
    assert result[1] is answer
    assert result[1].model_dump() == {'role': 'assistant', 'content': 'Previous solution', 'images': []}
