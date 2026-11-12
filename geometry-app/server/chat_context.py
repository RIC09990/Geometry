"""Bound model context without rewriting questions or classifying their intent.

The visible conversation remains untouched. Keep contiguous recent user turns,
and include only the newest upload group within those turns. This is deliberately
the same policy as the browser's chat-context builder.
"""
from typing import Any, Protocol, Sequence, TypeVar


MAX_CONTEXT_TURNS = 4
MAX_CONTEXT_MESSAGES = 8
MAX_CONTEXT_CHARACTERS = 12000


class _Message(Protocol):
    role: str
    content: str
    images: list[Any]

    def model_copy(self, *, update: dict[str, Any]) -> Any: ...


MessageT = TypeVar('MessageT', bound=_Message)


def prepare_chat_messages(messages: Sequence[MessageT]) -> list[MessageT]:
    """Select complete recent turns; never truncate the latest user message.

    A turn starts with a user message and includes any following assistant
    messages. A cancelled request may leave a user-only turn, which is retained
    as a unit too. Leading orphan assistant messages are not useful context.
    The final user is the current turn; normally this leaves up to three full
    historical user/assistant pairs plus that final message.

    Text length uses Unicode code points, matching Python ``len`` and the
    browser's ``Array.from(content).length``. If the current input alone exceeds
    the text budget, preserve it intact and omit historical turns.
    """
    if not messages or messages[-1].role != 'user':
        raise ValueError('Chat context must end with a user message')

    turns: list[list[MessageT]] = []
    for message in messages:
        if message.role == 'user':
            turns.append([message])
        elif turns:
            turns[-1].append(message)

    selected = [turns[-1]]
    message_count = len(turns[-1])
    character_count = sum(len(message.content) for message in turns[-1])
    for turn in reversed(turns[:-1]):
        turn_characters = sum(len(message.content) for message in turn)
        if (len(selected) >= MAX_CONTEXT_TURNS
                or message_count + len(turn) > MAX_CONTEXT_MESSAGES
                or character_count + turn_characters > MAX_CONTEXT_CHARACTERS):
            # Do not skip an oversized recent turn and resurrect older context.
            break
        selected.append(turn)
        message_count += len(turn)
        character_count += turn_characters

    retained = [message for turn in reversed(selected) for message in turn]
    newest_images = next((index for index in range(len(retained) - 1, -1, -1)
                          if retained[index].role == 'user' and retained[index].images), None)
    return [message.model_copy(update={'images': []})
            if message.images and index != newest_images else message
            for index, message in enumerate(retained)]
