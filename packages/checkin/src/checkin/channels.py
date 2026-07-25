"""The messaging seam.

One Protocol, so the questionnaire and the session are identical whether the
person is on WhatsApp, SMS or anything added later. Twilio is the only live
implementation: it carries both transports, so provider independence lives in this
Protocol rather than in a second integration nobody maintains.

Deliberately not VoiceChannel. A phone call is synchronous — ask, hear an answer.
A message conversation is not: send, then wait for a webhook that may arrive in
minutes or never. Collapsing the two would hide the case that matters most, which
is the reply that never comes.
"""

from typing import Protocol, runtime_checkable

from checkin.messages import ButtonMessage, TemplateMessage


@runtime_checkable
class ConversationChannel(Protocol):
    def send(self, to: str, message: TemplateMessage | ButtonMessage) -> str: ...
