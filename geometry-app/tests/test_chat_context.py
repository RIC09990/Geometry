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


def test_a_conversation_inside_the_high_water_budget_is_sent_whole():
    messages = [*pairs(6), user('current')]
    assert prepare_chat_messages(messages) == messages


def test_exceeding_the_budget_drops_whole_old_turns_back_to_the_trim_target():
    messages = [*pairs(14), user('current')]
    result = prepare_chat_messages(messages)
    assert result == messages[-11:]
    assert len(result) == 11


def test_latest_input_over_budget_is_complete_and_keeps_its_uploads():
    latest = user('current attachment text ' * 4000, 'page 1', 'page 2')
    result = prepare_chat_messages([user('old'), assistant('old answer'), latest])
    assert result == [latest]
    assert len(result[0].content) > 24000


def test_character_boundary_matches_the_browser_code_point_count():
    messages = [user('u' * 12000), assistant('a' * 12000), user('?')]
    assert prepare_chat_messages(messages) == [messages[-1]]
    messages = [user('😀' * 5000), assistant('角' * 5000), user('?')]
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


def test_images_outside_the_selected_turns_are_not_reintroduced():
    messages = [user('old upload', 'old page'), assistant('old answer'), *pairs(13), user('explain')]
    result = prepare_chat_messages(messages)
    assert result == messages[-11:]
    assert not any(message.images for message in result)


def test_whole_assistant_groups_are_never_split_at_the_message_limit():
    group = lambda index: [user(f'question {index}'), *(assistant(f'fragment {index}-{fragment}') for fragment in range(6))]
    messages = [*group(0), *group(1), *group(2), *group(3), user('current')]
    assert prepare_chat_messages(messages) == [*group(3), user('current')]


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
