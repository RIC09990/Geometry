"""Bound model context without rewriting questions or classifying their intent.

The visible conversation remains untouched. Keep complete user turns with their
uploads. This is deliberately the same policy as the browser's chat-context
builder: keep everything while it fits the high-water limits, then drop back to
the low-water limits in one step so the cached prompt prefix changes once per
compaction instead of once per turn.
"""
from typing import Any, Protocol, Sequence, TypeVar


KEEP_TURNS = 12
KEEP_MESSAGES = 24
KEEP_CHARACTERS = 24000
TRIM_TURNS = 6
TRIM_MESSAGES = 12
TRIM_CHARACTERS = 12000


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

    flat = [message for turn in turns for message in turn]
    if (len(turns) <= KEEP_TURNS and len(flat) <= KEEP_MESSAGES
            and _characters(flat) <= KEEP_CHARACTERS):
        return list(flat)

    selected = [turns[-1]]
    message_count = len(turns[-1])
    character_count = _characters(turns[-1])
    for turn in reversed(turns[:-1]):
        turn_characters = _characters(turn)
        if (len(selected) >= TRIM_TURNS
                or message_count + len(turn) > TRIM_MESSAGES
                or character_count + turn_characters > TRIM_CHARACTERS):
            # Do not skip an oversized recent turn and resurrect older context.
            break
        selected.append(turn)
        message_count += len(turn)
        character_count += turn_characters

    return [message for turn in reversed(selected) for message in turn]


def _characters(messages: Sequence[_Message]) -> int:
    return sum(len(message.content) for message in messages)

