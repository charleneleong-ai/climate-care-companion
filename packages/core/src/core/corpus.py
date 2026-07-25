import csv
from dataclasses import dataclass
from pathlib import Path

import yaml
from contracts import MedClass, Reason, ReasonCode

SEED_DIR = Path(__file__).resolve().parents[4] / "data" / "seed"


@dataclass(frozen=True, slots=True)
class ActionRow:
    reason_code: ReasonCode
    tier_min: str
    text: str
    escalate_to: str
    ordering: int


class Corpus:
    """The action and explanation corpus.

    Holds the only text the system is allowed to show or say. The voice agent in
    packages/checkin selects rows from `actions` and never composes, which is what
    keeps SC-1 greppable on a spoken surface (spec section 6).
    """

    def __init__(
        self,
        reasons: dict[ReasonCode, Reason],
        actions: tuple[ActionRow, ...],
        med_classes: dict[str, MedClass],
    ) -> None:
        self.reasons = reasons
        self.actions = actions
        self.med_classes = med_classes

    @classmethod
    def load(cls, directory: Path | None = None) -> "Corpus":
        target = directory or SEED_DIR
        reasons = cls.read_reasons(target / "reasons.yaml")
        missing = set(ReasonCode) - set(reasons)
        if missing:
            raise ValueError(f"missing reason text for: {sorted(missing)}")
        return cls(
            reasons=reasons,
            actions=cls.read_actions(target / "actions.csv"),
            med_classes=cls.read_med_classes(target / "med_classes.csv"),
        )

    @staticmethod
    def read_reasons(path: Path) -> dict[ReasonCode, Reason]:
        raw = yaml.safe_load(path.read_text()) or {}
        return {
            ReasonCode(key): Reason(
                code=ReasonCode(key),
                title=value["title"].strip(),
                explanation=value["explanation"].strip(),
                weight=0,
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
                row["drug_name"].lower(): MedClass(row["drug_class"])
                for row in csv.DictReader(fh)
            }

    def actions_for(self, code: ReasonCode) -> tuple[ActionRow, ...]:
        return tuple(row for row in self.actions if row.reason_code is code)

    def classify(self, drug_name: str) -> MedClass:
        """FR-14. An unknown drug is OTHER, never a KeyError — a caregiver's typo
        must not take the assessment down."""
        return self.med_classes.get(drug_name.lower(), MedClass.OTHER)
