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


def test_current_turn_and_three_complete_recent_turns_are_retained():
    messages = [message for i in range(6)
                for message in (user(f'question {i}'), assistant(f'answer {i}'))]
    messages.append(user('current'))
    result = prepare_chat_messages(messages)
    assert result == messages[-7:]
    assert len(result) <= 8
    assert result[0].role == 'user'
    assert all(a is b for a, b in zip(result, messages[-7:]))


def test_latest_input_over_budget_is_complete_and_keeps_its_uploads():
    latest = user('current attachment text ' * 4000, 'page 1', 'page 2')
    result = prepare_chat_messages([user('old'), assistant('old answer'), latest])
    assert result == [latest]
    assert result[0] is latest
    assert len(result[0].content) > 12000


def test_oversized_recent_turn_stops_history_without_skipping_to_older_turns():
    messages = [user('short older problem'), assistant('short older answer'),
                user('recent problem'), assistant('x' * 12000), user('follow-up')]
    assert prepare_chat_messages(messages) == [messages[-1]]


def test_character_boundary_is_exact_and_whole_turns_are_removed():
    messages = [user('u' * 3000), assistant('a' * 8999), user('?')]
    assert prepare_chat_messages(messages) == messages
    messages[1] = assistant('a' * 9000)
    assert prepare_chat_messages(messages) == [messages[-1]]


def test_unicode_budget_matches_browser_code_point_count():
    messages = [user('😀' * 3000), assistant('角' * 8999), user('?')]
    assert prepare_chat_messages(messages) == messages
    messages[1] = assistant('角' * 9000)
    assert prepare_chat_messages(messages) == [messages[-1]]


def test_followup_reuses_only_the_latest_retained_upload_group():
    old = user('first question', 'old page')
    recent = user('second question', 'new page 1', 'new page 2')
    messages = [old, assistant('first answer'), recent, assistant('second answer'), user('why?')]
    before = [message.model_dump() for message in messages]
    result = prepare_chat_messages(messages)
    assert result[0].images == []
    assert result[0] is not old
    assert result[2] is recent
    assert [image['name'] for image in result[2].images] == ['new page 1', 'new page 2']
    assert [message.model_dump() for message in messages] == before


def test_new_upload_supersedes_historical_uploads_without_deleting_their_text():
    messages = [user('old problem', 'old diagram'), assistant('old reasoning'),
                user('new problem', 'new diagram', 'new handwriting')]
    result = prepare_chat_messages(messages)
    assert [message.content for message in result] == [message.content for message in messages]
    assert [len(message.images) for message in result] == [0, 0, 2]
    assert result[-1] is messages[-1]
    assert len(messages[0].images) == 1


def test_images_outside_the_selected_context_are_not_reattached():
    messages = [user('old upload', 'old page'), assistant('old answer')]
    for index in range(3):
        messages.extend([user(f'question {index}'), assistant(f'answer {index}')])
    messages.append(user('explain'))
    result = prepare_chat_messages(messages)
    assert result == messages[-7:]
    assert not any(message.images for message in result)


def test_orphan_assistant_prefix_is_dropped_but_cancelled_user_turns_survive():
    messages = [assistant('orphan answer'), user('upload', 'worksheet'),
                user('extra detail'), assistant('response'), user('follow-up')]
    result = prepare_chat_messages(messages)
    assert result == messages[1:]
    assert result[0].images == messages[1].images


def test_eight_message_limit_preserves_entire_assistant_groups():
    group = [user('question'), *(assistant(f'continuation {i}') for i in range(6))]
    latest = user('follow-up')
    assert prepare_chat_messages([user('older'), assistant('older answer'), *group, latest]) == [*group, latest]
    assert prepare_chat_messages([*group, assistant('one too many'), latest]) == [latest]


@pytest.mark.parametrize('latest', ['换一道题', 'Here is a new problem', 'Check my answer', '继续解释'])
def test_content_is_not_rewritten_or_used_to_guess_a_topic_switch(latest):
    messages = [user('original question'), assistant('original answer'), user(latest)]
    assert prepare_chat_messages(messages) == messages


@pytest.mark.parametrize('messages', [[], [assistant('unfinished answer')]])
def test_invalid_request_end_is_rejected(messages):
    with pytest.raises(ValueError, match='user message'):
        prepare_chat_messages(messages)


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
