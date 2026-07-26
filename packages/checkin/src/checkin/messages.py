"""Channel-agnostic message value objects.

Modelled on WhatsApp's constraints because they are the strictest: a business
cannot open a conversation with free text, only with a template Meta has approved
in advance. That is a second validation gate on top of SC-1, and it happens to
match the constraint packages/checkin already works under — the system selects
from approved text, it never composes.
"""

from dataclasses import dataclass, replace
from pathlib import Path

import yaml

TEMPLATES_PATH = Path(__file__).resolve().parents[4] / "data" / "seed" / "whatsapp_templates.yaml"

ANSWER_BY_TOKEN: dict[str, bool | None] = {"yes": True, "no": False, "unsure": None}
TOKEN_BY_ANSWER: dict[bool | None, str] = {True: "yes", False: "no", None: "unsure"}

BUTTON_TITLE_MAX = 20
"""WhatsApp caps reply-button titles at 20 characters."""

BUTTON_COUNT_MAX = 3
"""WhatsApp caps interactive reply buttons at 3, which is exactly yes / no / unsure."""

BODY_TEXT_MAX = 1024


def encode_button_id(question_code: str, answer: bool | None) -> str:
    """Carry the question code in the button id.

    Replies arrive asynchronously and possibly out of order, so a bare yes is
    ambiguous. Binding the answer to its question at send time means a late reply
    to an earlier question cannot be recorded against the wrong one.
    """
    return f"{question_code}:{TOKEN_BY_ANSWER[answer]}"


def decode_button_id(button_id: str) -> tuple[str, bool | None]:
    code, _, token = button_id.partition(":")
    if not code or token not in ANSWER_BY_TOKEN:
        raise ValueError(f"unrecognised button id: {button_id!r}")
    return code, ANSWER_BY_TOKEN[token]


@dataclass(frozen=True, slots=True)
class ReplyButton:
    id: str
    title: str

    def __post_init__(self) -> None:
        if len(self.title) > BUTTON_TITLE_MAX:
            raise ValueError(f"button title {self.title!r} exceeds {BUTTON_TITLE_MAX} characters")


@dataclass(frozen=True, slots=True)
class TemplateMessage:
    """A business-initiated message. Must be pre-approved by Meta before use.

    The scaffold ships the template *text* so the wording is reviewable and covered
    by the SC-1 gate. Submitting it for approval is a manual step in Meta Business
    Manager and is not automatable.

    Declared variable names and bound values are separate fields on purpose. Merging
    them lets an unbound template send its own placeholder — "Hello first_name" to
    an 88-year-old — which is the kind of error that costs trust in the channel
    permanently. `bind` is the only way to produce a sendable template.
    """

    name: str
    language: str
    body: str
    """The approved wording, kept here so it is greppable and version-controlled.
    Must match what Meta approved, or the send is rejected."""
    variable_names: tuple[str, ...] = ()
    variables: tuple[str, ...] = ()

    @property
    def is_bound(self) -> bool:
        return len(self.variables) == len(self.variable_names)

    def bind(self, *values: str) -> "TemplateMessage":
        if len(values) != len(self.variable_names):
            raise ValueError(
                f"template {self.name} declares {len(self.variable_names)} variables "
                f"{self.variable_names} but was given {len(values)}"
            )
        return replace(self, variables=values)


@dataclass(frozen=True, slots=True)
class ButtonMessage:
    """A free-form interactive message. Only sendable inside the 24-hour window."""

    body: str
    buttons: tuple[ReplyButton, ...]

    def __post_init__(self) -> None:
        if not self.buttons:
            raise ValueError("an interactive message needs at least one button")
        if len(self.buttons) > BUTTON_COUNT_MAX:
            raise ValueError(
                f"WhatsApp allows at most {BUTTON_COUNT_MAX} reply buttons, got {len(self.buttons)}"
            )
        if len(self.body) > BODY_TEXT_MAX:
            raise ValueError(f"body exceeds {BODY_TEXT_MAX} characters")


class TemplateLibrary:
    """The approved-template corpus.

    Mirrors core.corpus.Corpus: the wording lives in version control so it is
    reviewable and greppable, because Meta's approval checks policy compliance, not
    clinical safety. SC-1 still applies.
    """

    def __init__(self, templates: dict[str, TemplateMessage]) -> None:
        self.templates = templates

    @classmethod
    def load(cls, path: Path | None = None) -> "TemplateLibrary":
        raw = yaml.safe_load((path or TEMPLATES_PATH).read_text()) or {}
        return cls(
            {
                key: TemplateMessage(
                    name=value["name"],
                    language=value["language"],
                    body=" ".join(value["body"].split()),
                    variable_names=tuple(value.get("variables", ())),
                )
                for key, value in raw.items()
            }
        )

    def get(self, key: str) -> TemplateMessage:
        if key not in self.templates:
            raise KeyError(
                f"no approved template named {key!r}. Templates must be added to "
                f"whatsapp_templates.yaml and approved in Meta Business Manager."
            )
        return self.templates[key]

    def opener_for(self, simplified: bool) -> TemplateMessage:
        return self.get("checkin_opener_simple" if simplified else "checkin_opener")


def question_buttons(question_code: str) -> tuple[ReplyButton, ...]:
    """Yes / No / Not sure.

    "Not sure" is a first-class answer rather than a fallback. Forcing a binary
    from someone who does not know produces a confident wrong value, and under
    SC-7's over-warn bias an honest unsure is safer than a guessed no.
    """
    return (
        ReplyButton(encode_button_id(question_code, True), "Yes"),
        ReplyButton(encode_button_id(question_code, False), "No"),
        ReplyButton(encode_button_id(question_code, None), "Not sure"),
    )
