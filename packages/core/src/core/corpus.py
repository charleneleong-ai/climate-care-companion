import csv
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from contracts import MedClass, ReasonCode

SEED_DIR = Path(__file__).resolve().parents[4] / "data" / "seed"

MEDICATION_PREFIX = "med_"

FORBIDDEN_MEDICATION_ADVICE = re.compile(
    r"\b(stop|stopping|reduce|reducing|skip|skipping|halt|halting|delay|delaying"
    r"|alter|altering|discontinue|discontinuing|double|miss|missing)\b",
    re.IGNORECASE,
)
"""SC-1: never advise stopping, reducing, delaying or altering a prescribed medicine.

Defined once, here, and enforced at load time. Every test that checks SC-1 imports
this constant rather than restating the word list — three copies with three
different word lists is how a safety gate silently weakens.

Deliberately excludes "lower", which appears legitimately when describing a
mechanism ("this medicine lowers blood flow to the skin") rather than giving
advice. A gate that fires on correct text teaches authors to write around it, which
costs more safety than the extra word buys.

This is a blunt instrument and not a substitute for SC-4: a registered pharmacist
must review these rules before use with any real patient.
"""

PROFESSIONALS = frozenset({"pharmacist", "gp"})
"""SC-1's other half: state the risk, then route. A medication risk with nobody to
call is not an action."""


@dataclass(frozen=True, slots=True)
class ReasonText:
    """Title and explanation for a reason code. Carries no weight — weights live in
    the rule tables, and duplicating them here would let the two drift."""

    title: str
    explanation: str


@dataclass(frozen=True, slots=True)
class ActionRow:
    reason_code: ReasonCode
    tier_min: str
    text: str
    escalate_to: str
    ordering: int

    @property
    def is_medication_advice(self) -> bool:
        return self.reason_code.startswith(MEDICATION_PREFIX)


class Corpus:
    """The action and explanation corpus.

    Holds the only text the system is allowed to show or say. The voice agent in
    packages/checkin selects rows from `actions` and never composes, which is what
    keeps SC-1 greppable on a spoken surface (spec section 6).
    """

    def __init__(
        self,
        reasons: dict[ReasonCode, ReasonText],
        actions: tuple[ActionRow, ...],
        med_classes: dict[str, MedClass],
    ) -> None:
        self.reasons = reasons
        self.actions = actions
        self.med_classes = med_classes

    @classmethod
    def load(cls, directory: Path | None = None) -> "Corpus":
        """Load and validate. A corpus that violates AC-3 or SC-1 does not load.

        Failing here rather than in a test means the safety property holds for every
        caller, including one that imports the corpus without running the suite.
        """
        target = directory or SEED_DIR
        corpus = cls(
            reasons=cls.read_reasons(target / "reasons.yaml"),
            actions=cls.read_actions(target / "actions.csv"),
            med_classes=cls.read_med_classes(target / "med_classes.csv"),
        )
        corpus.check_reason_text_complete()
        corpus.check_medication_safety()
        return corpus

    @staticmethod
    def read_reasons(path: Path) -> dict[ReasonCode, ReasonText]:
        raw = yaml.safe_load(path.read_text()) or {}
        return {
            ReasonCode(key): ReasonText(
                title=value["title"].strip(),
                explanation=value["explanation"].strip(),
            )
            for key, value in raw.items()
        }

    @staticmethod
    def read_actions(path: Path) -> tuple[ActionRow, ...]:
        with path.open(newline="") as fh:
            return tuple(
                ActionRow(
                    reason_code=ReasonCode(row["reason_code"]),
                    tier_min=row["tier_min"],
                    text=row["text"],
                    escalate_to=row["escalate_to"],
                    ordering=int(row["ordering"]),
                )
                for row in csv.DictReader(fh)
            )

    @staticmethod
    def read_med_classes(path: Path) -> dict[str, MedClass]:
        with path.open(newline="") as fh:
            return {
                row["drug_name"].lower(): MedClass(row["drug_class"]) for row in csv.DictReader(fh)
            }

    def check_reason_text_complete(self) -> None:
        missing = set(ReasonCode) - set(self.reasons)
        if missing:
            raise ValueError(f"missing reason text for: {sorted(missing)}")

    def check_medication_safety(self) -> None:
        """SC-1, enforced at load rather than only in CI."""
        for row in self.medication_actions():
            if FORBIDDEN_MEDICATION_ADVICE.search(row.text):
                raise ValueError(
                    f"SC-1 violation in {row.reason_code}: medication advice must never "
                    f"suggest changing a prescription — {row.text!r}"
                )
            if row.escalate_to not in PROFESSIONALS:
                raise ValueError(
                    f"SC-1 violation in {row.reason_code}: a medication risk must route "
                    f"to a pharmacist or GP, got {row.escalate_to!r}"
                )

    def medication_actions(self) -> tuple[ActionRow, ...]:
        return tuple(row for row in self.actions if row.is_medication_advice)

    def actions_for(self, code: ReasonCode) -> tuple[ActionRow, ...]:
        return tuple(row for row in self.actions if row.reason_code is code)

    def classify(self, drug_name: str) -> MedClass:
        """FR-14. An unknown drug is OTHER, never a KeyError — a caregiver's typo
        must not take the assessment down."""
        return self.med_classes.get(drug_name.lower(), MedClass.OTHER)
