import csv
from dataclasses import dataclass, fields
from enum import StrEnum, auto
from pathlib import Path

from contracts import Assessment, DateRange, ReasonCode, RedFlag, SelfReport, Tier
from core.corpus import FORBIDDEN_MEDICATION_ADVICE

QUESTIONS_PATH = Path(__file__).resolve().parents[4] / "data" / "seed" / "questions.csv"

TIER_BY_NAME: dict[str, Tier] = {
    "low": Tier.LOW,
    "elevated": Tier.ELEVATED,
    "high": Tier.HIGH,
    "severe": Tier.SEVERE,
}

ANSWER_FIELDS = frozenset({"bedroom_feels_hot", "drinking_fluids"})
"""SelfReport fields a question is allowed to populate. Validated at load against
the dataclass, so renaming a field cannot silently orphan a question."""


class Register(StrEnum):
    """How the questions are phrased.

    Not cosmetic: someone with dementia may not parse a two-clause question, and a
    question that is not understood produces an answer that is worse than no answer.
    """

    STANDARD = auto()
    SIMPLE = auto()


@dataclass(frozen=True, slots=True)
class QuestionRow:
    code: str
    reason_code: ReasonCode | None
    """None means always asked, subject to tier."""
    tier_min: Tier
    text: str
    text_simple: str
    answer_field: str | None
    red_flag: RedFlag | None
    red_flag_when: bool
    """Whether True or False indicates the flag. 'Have you passed water today?'
    flags on no; 'do you feel muddled?' flags on yes. Getting this backwards
    silently inverts an SC-3 screen, so it is data rather than inferred."""
    ordering: int

    def phrased(self, register: Register) -> str:
        return self.text_simple if register is Register.SIMPLE else self.text


@dataclass(frozen=True, slots=True)
class Question:
    code: str
    text: str
    answer_field: str | None
    red_flag: RedFlag | None
    red_flag_when: bool

    @property
    def is_red_flag_screen(self) -> bool:
        return self.red_flag is not None


@dataclass(frozen=True, slots=True)
class Questionnaire:
    """One person's questions for one window.

    Personalised by selection from a validated bank — never by generation. The same
    argument as CheckinScript: an unsupervised call to an 88-year-old about their
    health must be auditable line by line, and a composed question is not.
    """

    person_id: str
    window: DateRange
    register: Register
    questions: tuple[Question, ...]

    def to_self_report(self, answers: dict[str, bool | None]) -> SelfReport:
        """Fold answers into the contract L1 and L4 already consume.

        An empty answers map means the call was not answered — a first-class
        outcome, since a missed call during a risk window is precisely the
        condition the system exists to catch.
        """
        fields_set: dict[str, bool | None] = {}
        red_flags: list[RedFlag] = []

        for question in self.questions:
            answer = answers.get(question.code)
            if answer is None:
                continue
            if question.answer_field:
                fields_set[question.answer_field] = answer
            if question.red_flag is not None and answer is question.red_flag_when:
                red_flags.append(question.red_flag)

        return SelfReport(
            person_id=self.person_id,
            window=self.window,
            answered=bool(answers),
            bedroom_feels_hot=fields_set.get("bedroom_feels_hot"),
            drinking_fluids=fields_set.get("drinking_fluids"),
            red_flags=tuple(red_flags),
        )

    def conduct(self, voice) -> SelfReport:
        """Ask every question over a VoiceChannel and return the report.

        Dispatch, scheduling, retry and no-answer escalation remain Track A's —
        this only walks the questions once a channel is already connected.
        """
        answers = {q.code: voice.ask(q.text) for q in self.questions}
        return self.to_self_report(answers)


class QuestionBank:
    """The validated question corpus, and the builder that personalises it.

    Personalisation runs along four auditable axes: which questions (reason codes),
    how many (tier and register), how they are phrased (register), and what each
    answer means (answer_field and red_flag polarity). No axis involves composing
    new text.
    """

    MAX_BY_TIER: dict[Tier, int] = {
        Tier.LOW: 0,
        Tier.ELEVATED: 6,
        Tier.HIGH: 8,
        Tier.SEVERE: 8,
    }

    SIMPLE_REGISTER_MAX = 5
    """Fewer questions in the simplified register. A half-finished questionnaire is
    worse than a short complete one."""

    def __init__(self, rows: tuple[QuestionRow, ...]) -> None:
        self.rows = rows

    @classmethod
    def load(cls, path: Path | None = None) -> "QuestionBank":
        bank = cls(cls.read_rows(path or QUESTIONS_PATH))
        bank.check_answer_fields_exist()
        bank.check_no_medication_advice()
        return bank

    @staticmethod
    def read_rows(path: Path) -> tuple[QuestionRow, ...]:
        with path.open(newline="") as fh:
            return tuple(
                QuestionRow(
                    code=row["code"],
                    reason_code=ReasonCode(row["reason_code"]) if row["reason_code"] else None,
                    tier_min=TIER_BY_NAME[row["tier_min"]],
                    text=row["text"],
                    text_simple=row["text_simple"],
                    answer_field=row["answer_field"] or None,
                    red_flag=RedFlag(row["red_flag"]) if row["red_flag"] else None,
                    red_flag_when=row["red_flag_when"] != "no",
                    ordering=int(row["ordering"]),
                )
                for row in csv.DictReader(fh)
            )

    def check_answer_fields_exist(self) -> None:
        valid = {f.name for f in fields(SelfReport)} & ANSWER_FIELDS
        for row in self.rows:
            if row.answer_field and row.answer_field not in valid:
                raise ValueError(
                    f"{row.code} writes to {row.answer_field!r}, which is not a "
                    f"SelfReport field a question may populate"
                )

    def check_no_medication_advice(self) -> None:
        """SC-1 applies to questions too. A question is not a route around it."""
        for row in self.rows:
            for text in (row.text, row.text_simple):
                if FORBIDDEN_MEDICATION_ADVICE.search(text):
                    raise ValueError(
                        f"SC-1 violation in question {row.code}: a question must never "
                        f"suggest changing a prescription — {text!r}"
                    )

    def max_questions(self, tier: Tier, register: Register) -> int:
        cap = self.MAX_BY_TIER[tier]
        if register is Register.SIMPLE:
            return min(cap, self.SIMPLE_REGISTER_MAX)
        return cap

    @staticmethod
    def register_for(assessment: Assessment) -> Register:
        codes = {reason.code for reason in assessment.reasons}
        return Register.SIMPLE if ReasonCode.DEMENTIA in codes else Register.STANDARD

    def build_for(
        self, person_id: str, window: DateRange, assessment: Assessment
    ) -> Questionnaire:
        register = self.register_for(assessment)
        if assessment.tier is Tier.LOW:
            return Questionnaire(person_id, window, register, ())

        codes = {reason.code for reason in assessment.reasons}
        applicable = sorted(
            (
                row
                for row in self.rows
                if assessment.tier >= row.tier_min
                and (row.reason_code is None or row.reason_code in codes)
            ),
            key=lambda row: row.ordering,
        )

        selected = self.take_without_repeating(
            applicable, register, self.max_questions(assessment.tier, register)
        )
        return Questionnaire(
            person_id=person_id,
            window=window,
            register=register,
            questions=tuple(
                Question(
                    code=row.code,
                    text=row.phrased(register),
                    answer_field=row.answer_field,
                    red_flag=row.red_flag,
                    red_flag_when=row.red_flag_when,
                )
                for row in selected
            ),
        )

    @staticmethod
    def take_without_repeating(
        rows: list[QuestionRow], register: Register, limit: int
    ) -> list[QuestionRow]:
        """Deduplicate by phrasing, then apply the cap.

        Red-flag screens are exempt from the cap. SC-3 must not go unasked because
        the person happened to trigger a lot of other reason codes.
        """
        seen: set[str] = set()
        ordinary: list[QuestionRow] = []
        red_flags: list[QuestionRow] = []
        for row in rows:
            text = row.phrased(register)
            if text in seen:
                continue
            seen.add(text)
            (red_flags if row.red_flag is not None else ordinary).append(row)

        kept = ordinary[:limit] + red_flags
        return sorted(kept, key=lambda row: row.ordering)
