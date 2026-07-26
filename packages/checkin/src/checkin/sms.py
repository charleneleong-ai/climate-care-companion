"""SMS rendering.

Not a downgrade from WhatsApp — for this population it is the wider net. The 85+
cohort is the group least likely to have a smartphone at all, and a basic handset
takes SMS. WhatsApp buys interactive buttons; SMS buys reach.

The same ButtonMessage renders for both. Questionnaire and session are unchanged,
which is the point of the channel abstraction.

Sending is Twilio's job — it carries SMS and WhatsApp on one API, so a second
gateway integration would be duplication rather than independence. If a UK
public-sector deployment wants GOV.UK Notify instead (free at those volumes, and
it keeps health-adjacent messages off a US commercial gateway), it implements
ConversationChannel and nothing else changes.
"""

from checkin.messages import ButtonMessage, TemplateMessage, encode_button_id

GSM7_SEGMENT = 160
"""Single-segment limit for the GSM-7 alphabet. Concatenated messages cost a
segment each and arrive as one message on most handsets, but not all — an older
phone may show three fragments out of order."""

MAX_SEGMENTS = 2
"""A check-in question that needs three fragments is too long to answer."""

REPLY_TOKENS: dict[str, bool | None] = {
    "yes": True,
    "y": True,
    "1": True,
    "yeah": True,
    "yep": True,
    "no": False,
    "n": False,
    "2": False,
    "nope": False,
    "unsure": None,
    "3": None,
    "dunno": None,
    "?": None,
}
"""Deliberately generous on the yes/no side. Someone typing on a numeric keypad at
eighty-eight will not match a strict grammar, and a rejected reply reads to them as
being ignored."""


class SmsFormatter:
    """Renders channel-agnostic messages as plain text, and parses replies back.

    SMS has no interactive buttons, so the options become numbered text and the
    reply is free text mapped onto the same closed set the voice channel uses.
    """

    @staticmethod
    def render(message: TemplateMessage | ButtonMessage) -> str:
        if isinstance(message, TemplateMessage):
            if not message.is_bound:
                raise ValueError(
                    f"template {message.name} has unbound variables "
                    f"{message.variable_names}. Call bind() first."
                )
            body = message.body
            for index, value in enumerate(message.variables, start=1):
                body = body.replace(f"{{{{{index}}}}}", value)
            return body
        options = " ".join(
            f"{n}={button.title}" for n, button in enumerate(message.buttons, start=1)
        )
        return f"{message.body}\nReply {options}"

    @staticmethod
    def segments(text: str) -> int:
        return max(1, -(-len(text) // GSM7_SEGMENT))

    @classmethod
    def check_length(cls, text: str) -> None:
        if cls.segments(text) > MAX_SEGMENTS:
            raise ValueError(
                f"message is {cls.segments(text)} SMS segments and will fragment: {text!r}"
            )

    @staticmethod
    def parse_reply(text: str, question_code: str) -> str | None:
        """Map a free-text reply onto a button id, or None if unrecognised.

        Unrecognised is not an answer and never a guess. It follows the same rule as
        the voice channel: silence and confusion are escalated, not interpreted.
        """
        token = text.strip().lower().rstrip(".!")
        if token not in REPLY_TOKENS:
            return None
        return encode_button_id(question_code, REPLY_TOKENS[token])
