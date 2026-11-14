"""Keep the complete conversation for the model without rewriting questions.

The visible conversation is untouched and every retained turn, including its
uploads, is sent as-is. Length is bounded by compaction: older turns leave the
request only after they were summarized into the stored summary, so the cached
prompt prefix changes when compaction runs instead of every turn.
"""
from typing import Any, Protocol, Sequence, TypeVar


class _Message(Protocol):
    role: str
    content: str
    images: list[Any]


MessageT = TypeVar('MessageT', bound=_Message)


def prepare_chat_messages(messages: Sequence[MessageT]) -> list[MessageT]:
    """Return every message from the first user message on.

    A cancelled request may leave a user-only turn, which is retained as a unit
    too. Leading orphan assistant messages are not useful context.
    """
    if not messages or messages[-1].role != 'user':
        raise ValueError('Chat context must end with a user message')

    start = next(index for index, message in enumerate(messages) if message.role == 'user')
    return list(messages[start:])
