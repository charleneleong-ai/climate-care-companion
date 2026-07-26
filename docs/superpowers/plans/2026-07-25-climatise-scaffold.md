# Climatise Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a uv-workspace scaffold where `contracts/` and `core/` are frozen and green, every other layer is a typed stub with a red test, and three contributors plus unlimited data contributors can work in parallel without blocking each other.

**Architecture:** Pure-Python layered core. `contracts/` defines every type crossing a layer boundary and depends on nothing. `core/` implements L2 vulnerability and L3 risk fusion as deterministic classes with no I/O and no clock. Everything else — exposure ingest, predictors, actions, voice check-in, allocation, org views — depends on `contracts/` and is independently replaceable. Data (personas, geography, action corpus) lives in globbed, schema-validated YAML/CSV so contributors can add content without editing Python.

**Tech Stack:** Python 3.13, uv workspace, pydantic v2 (data-file validation only), pytest, ruff, FastAPI, httpx, PyYAML.

## Global Constraints

- Python 3.13+. Modern syntax: `|` unions, `match`, built-in generics.
- Type hints on every signature, params **and** return, with explicit generic parameters: `dict[str, Any]` not `dict`, `tuple[Reason, ...]` not `tuple`.
- **Cohesive classes for components, backends and stateful workflows.** Loaders, scorers, engines and channels are classes. Keep only small stateless transformations (`haversine_km`) as functions, where a class would add ceremony.
- **No leading underscores** on module-level constants, classes, or reusable helpers. Reserve `_` for instance attributes and genuinely-private methods. Fold loose helpers into their owning class as `@staticmethod`.
- `packages/contracts/` has **zero** third-party dependencies. Stdlib only.
- `packages/core/` imports **only** `contracts` and stdlib. No I/O, no database, no `datetime.now()`, no network. AC-1's "pure function" requirement is satisfied by determinism and the absence of I/O — every input arrives as an argument.
- Every reason code must map to ≥1 action row, asserted at load time. (AC-3)
- Ruff complexity gate: `C901` max-complexity 10, `PLR0915` max-statements 50. Complexity-only ruleset.
- All modelled values labelled modelled wherever displayed. (SC-5)
- Imports at top of file. No function-local imports without a documented reason.
- Conventional commits. No `Co-Authored-By` trailers.
- Every stub raises `NotImplementedError` naming the owning track.

---

## File Structure

| Path | Responsibility | Principal class |
|---|---|---|
| `packages/contracts/enums.py` | Every enum crossing a boundary | — |
| `packages/contracts/models.py` | Frozen dataclasses | — |
| `packages/core/corpus.py` | Reason text, action corpus, med classes | `Corpus` |
| `packages/core/rules.py` | §8.1/§8.2 rule tables as data | `ExposureRule`, `VulnerabilityRule` |
| `packages/core/vulnerability.py` | L2 | `VulnerabilityScorer` |
| `packages/core/scoring.py` | L3 fusion, §8.4/§8.5 | `RiskScorer` |
| `packages/exposure/indoor.py` | FR-11 + self-report correction | `IndoorModel` |
| `packages/exposure/normalise.py` | FR-07/08/09 | `ExposureNormaliser` |
| `packages/persons/loader.py` | Persona YAML discovery | `PersonaLoader` |
| `packages/geography/loader.py` | Locality YAML discovery | `GeographyLoader` |
| `packages/predictors/base.py` | Seam | `Predictor` Protocol, `EpisodeForecast` |
| `packages/predictors/heatwave.py` | Lead-time engine | `ThresholdHeatwave`, `EnsembleHeatwave` |
| `packages/checkin/script.py` | Closed utterance selection | `CheckinScript` |
| `packages/checkin/voice.py` | Telephony seam | `VoiceChannel` Protocol, `ConsoleVoice` |
| `packages/actions/checklist.py` | L4 checklist | `ChecklistBuilder` (stub) |
| `packages/actions/notify.py` | FR-21/22 | `NotificationPolicy` (stub) |
| `packages/allocation/distance.py` | Haversine | *(function — class is ceremony)* |
| `packages/allocation/plans.py` | Ranking, coverage, siting | `AllocationEngine` |
| `packages/org/models.py` | Tenancy tables | `Org`, `Cohort`, `CohortMember` |
| `packages/org/views.py` | L6 aggregations | `CouncilView`, `HospitalView`, `CareHomeView` (stubs) |
| `services/api/main.py` | Read path | — |

---

## Task 1: Workspace, tooling and CI

**Files:**
- Create: `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `README.md`

**Interfaces:**
- Consumes: nothing
- Produces: `uv run pytest` and `uv run ruff check .` both work from repo root

- [ ] **Step 1: Root workspace manifest**

```toml
# pyproject.toml
[project]
name = "climatise"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["climatise-contracts", "climatise-core"]

[tool.uv.workspace]
members = ["packages/*", "services/*"]

[tool.uv.sources]
climatise-contracts = { workspace = true }
climatise-core = { workspace = true }

[dependency-groups]
dev = ["pytest>=8.3", "ruff>=0.8", "pre-commit>=4.0", "pytest-cov>=6.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
# Complexity-only ruleset: never churns existing style.
select = ["C901", "PLR0915"]

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.pylint]
max-statements = 50
```

- [ ] **Step 2: Pre-commit config**

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-yaml
```

- [ ] **Step 3: CI workflow**

```yaml
# .github/workflows/ci.yml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.13"
      - run: uv sync --all-packages
      - run: uv run ruff check .
      - name: Gates that must never go red
        run: uv run pytest tests/verification -v
      - name: Full suite (stubs expected red)
        run: uv run pytest tests -v || true
```

- [ ] **Step 4: Verify tooling runs**

Run: `uv sync --all-packages && uv run ruff check .`
Expected: ruff passes; uv creates `.venv`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .pre-commit-config.yaml .github/ README.md
git commit -m "chore: uv workspace, ruff complexity gate, CI"
```

---

## Task 2: Contracts — enums

**Files:**
- Create: `packages/contracts/pyproject.toml`, `packages/contracts/src/contracts/__init__.py`, `packages/contracts/src/contracts/enums.py`
- Test: `tests/contracts/test_enums.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Tier`, `ReasonCode`, `AlertLevel`, `ExposureSource`, `AgeBand`, `MedClass`, `Condition`, `RedFlag`, `OrgType`, `DwellingType`, `Aspect` — importable from `contracts`

- [ ] **Step 1: Write the failing test**

```python
# tests/contracts/test_enums.py
import pytest
from contracts import AgeBand, ExposureSource, MedClass, ReasonCode, Tier

EXPOSURE_CODES = {
    "NIGHT_NO_RECOVERY",
    "BEDROOM_UNSAFE",
    "BEDROOM_WARM",
    "PEAK_HEAT",
    "SUSTAINED_SPELL",
    "INDOOR_BELOW_18",
    "INDOOR_BELOW_16",
    "INDOOR_BELOW_12",
}
VULNERABILITY_CODES = {
    "AGE_85_PLUS",
    "AGE_75_84",
    "LIVES_ALONE",
    "DEMENTIA",
    "CARDIOVASCULAR",
    "RENAL",
    "RESPIRATORY",
    "MOBILITY_LIMITED",
    "MED_LITHIUM",
    "MED_DIURETIC",
    "MED_ANTICHOLINERGIC",
    "MED_ANTIPSYCHOTIC",
    "MED_ACE_ARB",
    "MED_BETA_BLOCKER",
    "MED_SSRI",
}


def test_reason_codes_match_spec_tables_exactly():
    assert {c.name for c in ReasonCode} == EXPOSURE_CODES | VULNERABILITY_CODES


def test_tiers_order_low_to_severe():
    assert [t.name for t in Tier] == ["LOW", "ELEVATED", "HIGH", "SEVERE"]
    assert Tier.LOW < Tier.SEVERE


@pytest.mark.parametrize("member", ["LIVE", "ARCHIVE", "CACHE", "FIXTURE", "SELF_REPORT"])
def test_exposure_source_records_provenance(member):
    assert member in ExposureSource.__members__


def test_med_classes_cover_spec_8_3():
    assert {c.name for c in MedClass} >= {
        "DIURETIC",
        "ANTICHOLINERGIC",
        "BETA_BLOCKER",
        "ACE_ARB",
        "ANTIPSYCHOTIC",
        "SSRI",
        "LITHIUM",
        "HEAT_SENSITIVE",
    }


def test_age_bands_are_ordered_and_disjoint():
    assert [b.name for b in AgeBand] == ["UNDER_65", "B65_74", "B75_84", "B85_PLUS"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/contracts/test_enums.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contracts'`

- [ ] **Step 3: Write the package**

```toml
# packages/contracts/pyproject.toml
[project]
name = "climatise-contracts"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = []          # zero third-party deps, permanently

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/contracts"]
```

```python
# packages/contracts/src/contracts/enums.py
from enum import IntEnum, StrEnum, auto


class Tier(IntEnum):
    LOW = 0
    ELEVATED = 1
    HIGH = 2
    SEVERE = 3


class ReasonCode(StrEnum):
    # Exposure — spec 8.1
    NIGHT_NO_RECOVERY = auto()
    BEDROOM_UNSAFE = auto()
    BEDROOM_WARM = auto()
    PEAK_HEAT = auto()
    SUSTAINED_SPELL = auto()
    INDOOR_BELOW_18 = auto()
    INDOOR_BELOW_16 = auto()
    INDOOR_BELOW_12 = auto()
    # Vulnerability — spec 8.2
    AGE_85_PLUS = auto()
    AGE_75_84 = auto()
    LIVES_ALONE = auto()
    DEMENTIA = auto()
    CARDIOVASCULAR = auto()
    RENAL = auto()
    RESPIRATORY = auto()
    MOBILITY_LIMITED = auto()
    MED_LITHIUM = auto()
    MED_DIURETIC = auto()
    MED_ANTICHOLINERGIC = auto()
    MED_ANTIPSYCHOTIC = auto()
    MED_ACE_ARB = auto()
    MED_BETA_BLOCKER = auto()
    MED_SSRI = auto()


class AlertLevel(StrEnum):
    NONE = auto()
    YELLOW = auto()
    AMBER = auto()
    RED = auto()
    NOT_CHECKED = auto()  # FR-12 graceful degradation


class ExposureSource(StrEnum):
    """Provenance only. Never changes behaviour — see AC-5."""

    LIVE = auto()
    ARCHIVE = auto()
    CACHE = auto()
    FIXTURE = auto()
    SELF_REPORT = auto()


class AgeBand(StrEnum):
    UNDER_65 = auto()
    B65_74 = auto()
    B75_84 = auto()
    B85_PLUS = auto()


class Condition(StrEnum):
    DEMENTIA = auto()
    CARDIOVASCULAR = auto()
    RENAL = auto()
    RESPIRATORY = auto()


class MedClass(StrEnum):
    DIURETIC = auto()
    ANTICHOLINERGIC = auto()
    BETA_BLOCKER = auto()
    ACE_ARB = auto()
    ANTIPSYCHOTIC = auto()
    SSRI = auto()
    LITHIUM = auto()
    HEAT_SENSITIVE = auto()
    OTHER = auto()


class RedFlag(StrEnum):
    """SC-3 clinical red flags. This set only — nothing else routes to 999."""

    UNROUSABLE = auto()
    CONFUSION = auto()
    NO_URINE_OUTPUT = auto()
    HOT_DRY_SKIN = auto()


class OrgType(StrEnum):
    COUNCIL = auto()
    HOSPITAL = auto()
    CARE_HOME = auto()
    ICB = auto()  # declared, unimplemented


class DwellingType(StrEnum):
    HOUSE = auto()
    FLAT = auto()
    BUNGALOW = auto()
    CARE_HOME = auto()


class Aspect(StrEnum):
    NORTH = auto()
    EAST = auto()
    SOUTH = auto()
    WEST = auto()
```

```python
# packages/contracts/src/contracts/__init__.py
from contracts.enums import (
    AgeBand,
    AlertLevel,
    Aspect,
    Condition,
    DwellingType,
    ExposureSource,
    MedClass,
    OrgType,
    RedFlag,
    ReasonCode,
    Tier,
)

__all__ = [
    "AgeBand",
    "AlertLevel",
    "Aspect",
    "Condition",
    "DwellingType",
    "ExposureSource",
    "MedClass",
    "OrgType",
    "RedFlag",
    "ReasonCode",
    "Tier",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv sync --all-packages && uv run pytest tests/contracts/test_enums.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/contracts tests/contracts
git commit -m "feat(contracts): enums for tiers, reason codes and provenance"
```

---

## Task 3: Contracts — frozen models

**Files:**
- Create: `packages/contracts/src/contracts/models.py`
- Modify: `packages/contracts/src/contracts/__init__.py`
- Test: `tests/contracts/test_models.py`

**Interfaces:**
- Consumes: `contracts.enums`
- Produces: `DateRange`, `Med`, `Person`, `Place`, `ExposureFeatures`, `VulnerabilityProfile`, `Reason`, `Assessment`, `SelfReport`

- [ ] **Step 1: Write the failing test**

```python
# tests/contracts/test_models.py
import dataclasses
from datetime import date

import pytest
from contracts import (
    AgeBand,
    AlertLevel,
    Assessment,
    ExposureFeatures,
    ExposureSource,
    Person,
    Reason,
    ReasonCode,
    Tier,
    VulnerabilityProfile,
)

MODELS = [ExposureFeatures, Assessment, Person, Reason, VulnerabilityProfile]


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_models_are_frozen_and_slotted(model):
    assert model.__dataclass_params__.frozen, f"{model.__name__} must be immutable"
    assert getattr(model, "__slots__", None) is not None


def test_assessment_reasons_is_a_tuple_and_cannot_be_mutated():
    a = Assessment(
        tier=Tier.LOW, risk_score=0.0, exposure_score=0, vulnerability_score=7, reasons=()
    )
    assert isinstance(a.reasons, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.tier = Tier.SEVERE


def test_exposure_features_carries_provenance_and_alert():
    e = ExposureFeatures(
        date=date(2025, 7, 19),
        overnight_min=17.0,
        peak_apparent=29.0,
        peak_air=29.0,
        hours_above_26=6,
        indoor_night_est=24.6,
        indoor_day_est=25.85,
        spell_day=3,
        alert_level=AlertLevel.NONE,
        source=ExposureSource.FIXTURE,
    )
    assert e.source is ExposureSource.FIXTURE
    assert e.alert_level is AlertLevel.NONE


def test_person_collections_default_to_empty_not_none():
    p = Person(
        id="p1", name="Doris", age_band=AgeBand.B85_PLUS, lives_alone=True, mobility_limited=False
    )
    assert p.medications == ()
    assert p.conditions == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/contracts/test_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Assessment'`

- [ ] **Step 3: Write the models**

```python
# packages/contracts/src/contracts/models.py
from dataclasses import dataclass, field
from datetime import date

from contracts.enums import (
    AgeBand,
    AlertLevel,
    Aspect,
    Condition,
    DwellingType,
    ExposureSource,
    MedClass,
    RedFlag,
    ReasonCode,
    Tier,
)


@dataclass(frozen=True, slots=True)
class DateRange:
    start: date
    end: date


@dataclass(frozen=True, slots=True)
class Med:
    drug_name: str
    drug_class: MedClass


@dataclass(frozen=True, slots=True)
class Person:
    id: str
    name: str
    age_band: AgeBand
    lives_alone: bool
    mobility_limited: bool
    conditions: tuple[Condition, ...] = field(default=())
    medications: tuple[Med, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class Place:
    person_id: str
    postcode: str
    lat: float
    lon: float
    admin_district: str
    region: str
    dwelling_type: DwellingType
    floor: int
    aspect: Aspect
    has_cooling: bool
    heating_affordable: bool
    dwelling_offset: float


@dataclass(frozen=True, slots=True)
class ExposureFeatures:
    """L1 to L3. The only thing the scoring core knows about weather."""

    date: date
    overnight_min: float
    peak_apparent: float
    peak_air: float
    hours_above_26: int
    indoor_night_est: float  # modelled — SC-5
    indoor_day_est: float  # modelled — SC-5
    spell_day: int
    alert_level: AlertLevel
    source: ExposureSource


@dataclass(frozen=True, slots=True)
class Reason:
    code: ReasonCode
    title: str
    explanation: str
    weight: int


@dataclass(frozen=True, slots=True)
class VulnerabilityProfile:
    person_id: str
    score: int
    codes: tuple[ReasonCode, ...]


@dataclass(frozen=True, slots=True)
class Assessment:
    """L3 output. AC-2: nothing downstream re-derives risk from raw exposure."""

    tier: Tier
    risk_score: float
    exposure_score: int
    vulnerability_score: int
    reasons: tuple[Reason, ...]


@dataclass(frozen=True, slots=True)
class SelfReport:
    """Voice check-in outcome. Never enters risk fusion — see spec section 6."""

    person_id: str
    window: DateRange
    answered: bool
    bedroom_feels_hot: bool | None = None
    drinking_fluids: bool | None = None
    red_flags: tuple[RedFlag, ...] = field(default=())
    transcript_ref: str | None = None  # pointer, never content
```

Add every new name to `contracts/__init__.py`'s import block and `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/contracts -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/contracts tests/contracts
git commit -m "feat(contracts): frozen models for the layer boundaries"
```

---

## Task 4: The Corpus — reason text, actions, medication classes

**Files:**
- Create: `packages/core/pyproject.toml`, `packages/core/src/core/corpus.py`, `data/seed/reasons.yaml`, `data/seed/actions.csv`, `data/seed/med_classes.csv`
- Test: `tests/core/test_corpus.py`

**Interfaces:**
- Consumes: `contracts.ReasonCode`
- Produces: `ActionRow` dataclass; `Corpus` with classmethod `load(directory: Path | None = None) -> Corpus`, properties `reasons: dict[ReasonCode, Reason]`, `actions: tuple[ActionRow, ...]`, `med_classes: dict[str, MedClass]`, and methods `actions_for(code: ReasonCode) -> tuple[ActionRow, ...]`, `classify(drug_name: str) -> MedClass`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_corpus.py
import re

import pytest
from contracts import MedClass, ReasonCode
from core.corpus import Corpus

FORBIDDEN = re.compile(r"\b(stop|reduce|skip|halt|delay|alter)\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return Corpus.load()


def test_every_reason_code_has_title_and_explanation(corpus):
    assert set(corpus.reasons) == set(ReasonCode)
    for code, reason in corpus.reasons.items():
        assert reason.title.strip(), f"{code} has an empty title"
        assert reason.explanation.strip(), f"{code} has an empty explanation"


def test_every_reason_code_maps_to_at_least_one_action(corpus):
    """AC-3: a reason code with no action is a specification defect."""
    missing = [c for c in ReasonCode if not corpus.actions_for(c)]
    assert not missing, f"reason codes with no action: {sorted(missing)}"


def test_medication_actions_never_advise_altering_a_prescription(corpus):
    """SC-1. Zero matches required."""
    offending = [
        (row.reason_code, row.text)
        for row in corpus.actions
        if row.reason_code.startswith("med_") and FORBIDDEN.search(row.text)
    ]
    assert not offending, f"SC-1 violation: {offending}"


@pytest.mark.parametrize(
    "drug,expected",
    [
        ("furosemide", MedClass.DIURETIC),
        ("ramipril", MedClass.ACE_ARB),
        ("lithium carbonate", MedClass.LITHIUM),
        ("oxybutynin", MedClass.ANTICHOLINERGIC),
        ("bisoprolol", MedClass.BETA_BLOCKER),
        ("sertraline", MedClass.SSRI),
        ("olanzapine", MedClass.ANTIPSYCHOTIC),
        ("insulin", MedClass.HEAT_SENSITIVE),
    ],
)
def test_classify_resolves_spec_8_3_examples(corpus, drug, expected):
    assert corpus.classify(drug) is expected


def test_classify_is_case_insensitive(corpus):
    assert corpus.classify("Furosemide") is MedClass.DIURETIC


def test_unknown_drug_classifies_as_other_rather_than_raising(corpus):
    assert corpus.classify("a drug nobody has heard of") is MedClass.OTHER


def test_load_raises_when_a_reason_code_is_missing_from_the_yaml(tmp_path):
    (tmp_path / "reasons.yaml").write_text("bedroom_warm:\n  title: t\n  explanation: e\n")
    (tmp_path / "actions.csv").write_text("reason_code,tier_min,text,escalate_to,ordering\n")
    (tmp_path / "med_classes.csv").write_text("drug_name,drug_class\n")
    with pytest.raises(ValueError, match="missing reason text"):
        Corpus.load(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_corpus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core'`

- [ ] **Step 3: Write the data files and the Corpus class**

`data/seed/reasons.yaml` — one entry per `ReasonCode`:

```yaml
bedroom_warm:
  title: "Bedroom warmer than is restful"
  explanation: >
    The modelled overnight bedroom temperature is between 24 and 26 degrees.
    Sleep is disrupted above 24, and the body does not recover from daytime heat.
night_no_recovery:
  title: "No overnight cooling"
  explanation: >
    The outdoor minimum stays at or above 20 degrees overnight, so there is no
    window during which the home can cool down.
med_diuretic:
  title: "Diuretic increases fluid and salt loss"
  explanation: >
    This medicine increases fluid and electrolyte loss, which compounds
    dehydration in hot weather.
# ... one entry for every member of ReasonCode
```

`data/seed/actions.csv` — medication rows state the risk and route to a professional; they never mention changing a dose:

```csv
reason_code,tier_min,text,escalate_to,ordering
bedroom_warm,elevated,"Open windows on the shaded side after sunset and close curtains during the day.",,10
night_no_recovery,elevated,"Move the bed to the coolest room in the home for the next few nights.",,20
med_diuretic,elevated,"This medicine increases fluid loss. Ask the pharmacist whether fluid intake should change in this heat. Keep taking it as prescribed.",pharmacist,30
med_lithium,high,"Dehydration raises lithium levels. Speak to the pharmacist or GP today. Keep taking it as prescribed.",pharmacist,5
```

```python
# packages/core/src/core/corpus.py
import csv
from dataclasses import dataclass
from pathlib import Path

import yaml
from contracts import MedClass, Reason, ReasonCode

SEED_DIR = Path(__file__).resolve().parents[4] / "data" / "seed"


@dataclass(frozen=True, slots=True)
class ActionRow:
    reason_code: str
    tier_min: str
    text: str
    escalate_to: str
    ordering: int


class Corpus:
    """The action and explanation corpus. A backend: loads once, answers questions.

    Holds the only text the system is allowed to show or say. The voice agent in
    packages/checkin selects from `actions` and never composes — see spec section 6.
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
                title=value["title"],
                explanation=value["explanation"].strip(),
                weight=0,
            )
            for key, value in raw.items()
        }

    @staticmethod
    def read_actions(path: Path) -> tuple[ActionRow, ...]:
        with path.open() as fh:
            return tuple(
                ActionRow(
                    row["reason_code"],
                    row["tier_min"],
                    row["text"],
                    row["escalate_to"],
                    int(row["ordering"]),
                )
                for row in csv.DictReader(fh)
            )

    @staticmethod
    def read_med_classes(path: Path) -> dict[str, MedClass]:
        with path.open() as fh:
            return {
                row["drug_name"].lower(): MedClass(row["drug_class"]) for row in csv.DictReader(fh)
            }

    def actions_for(self, code: ReasonCode) -> tuple[ActionRow, ...]:
        return tuple(row for row in self.actions if row.reason_code == code)

    def classify(self, drug_name: str) -> MedClass:
        """FR-14. Unknown drugs are OTHER, never a KeyError — a caregiver's typo
        must not take the assessment down."""
        return self.med_classes.get(drug_name.lower(), MedClass.OTHER)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/test_corpus.py -v`
Expected: PASS. If the AC-3 test fails, add the missing action rows — that failure is the gate working.

- [ ] **Step 5: Commit**

```bash
git add data/seed packages/core tests/core
git commit -m "feat(core): Corpus with AC-3 coverage and SC-1 safety gates"
```

---

## Task 5: L2 vulnerability scoring

**Files:**
- Create: `packages/core/src/core/rules.py`, `packages/core/src/core/vulnerability.py`
- Test: `tests/core/test_vulnerability.py`

**Interfaces:**
- Consumes: `contracts.Person`
- Produces: `VulnerabilityRule` dataclass, `VULNERABILITY_RULES: tuple[VulnerabilityRule, ...]`, `VulnerabilityScorer` with `profile(person: Person) -> VulnerabilityProfile`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_vulnerability.py
import pytest
from contracts import AgeBand, Condition, Med, MedClass, Person, ReasonCode
from core.vulnerability import VulnerabilityScorer


def person(**kw) -> Person:
    base = dict(
        id="p", name="P", age_band=AgeBand.UNDER_65, lives_alone=False, mobility_limited=False
    )
    return Person(**(base | kw))


DORIS = person(
    id="doris",
    name="Doris",
    age_band=AgeBand.B85_PLUS,
    lives_alone=True,
    conditions=(Condition.DEMENTIA,),
    medications=(Med("furosemide", MedClass.DIURETIC), Med("ramipril", MedClass.ACE_ARB)),
)


@pytest.fixture(scope="module")
def scorer() -> VulnerabilityScorer:
    return VulnerabilityScorer()


def test_doris_scores_ten_per_spec_8_6(scorer):
    p = scorer.profile(DORIS)
    assert p.score == 10
    assert set(p.codes) == {
        ReasonCode.AGE_85_PLUS,
        ReasonCode.LIVES_ALONE,
        ReasonCode.DEMENTIA,
        ReasonCode.MED_DIURETIC,
        ReasonCode.MED_ACE_ARB,
    }


@pytest.mark.parametrize(
    "band,code,weight",
    [(AgeBand.B85_PLUS, ReasonCode.AGE_85_PLUS, 3), (AgeBand.B75_84, ReasonCode.AGE_75_84, 2)],
)
def test_age_bands_score_per_spec_8_2(scorer, band, code, weight):
    p = scorer.profile(person(age_band=band))
    assert p.codes == (code,)
    assert p.score == weight


def test_age_bands_are_mutually_exclusive(scorer):
    assert ReasonCode.AGE_75_84 not in scorer.profile(person(age_band=AgeBand.B85_PLUS)).codes


def test_medication_scores_on_class_not_drug_name(scorer):
    """FR-14. Two different diuretics are still one diuretic flag."""
    p = scorer.profile(
        person(
            medications=(
                Med("furosemide", MedClass.DIURETIC),
                Med("bendroflumethiazide", MedClass.DIURETIC),
            )
        )
    )
    assert p.codes.count(ReasonCode.MED_DIURETIC) == 1
    assert p.score == 2


def test_person_with_no_vulnerabilities_scores_zero(scorer):
    p = scorer.profile(person())
    assert p.score == 0
    assert p.codes == ()


def test_profile_carries_the_person_id_through(scorer):
    assert scorer.profile(DORIS).person_id == "doris"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_vulnerability.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.vulnerability'`

- [ ] **Step 3: Implement the rule table and the scorer**

```python
# packages/core/src/core/rules.py
from collections.abc import Callable
from dataclasses import dataclass

from contracts import (
    AgeBand,
    Condition,
    ExposureFeatures,
    MedClass,
    Person,
    ReasonCode,
)


@dataclass(frozen=True, slots=True)
class VulnerabilityRule:
    code: ReasonCode
    predicate: Callable[[Person], bool]
    weight: int


@dataclass(frozen=True, slots=True)
class ExposureRule:
    code: ReasonCode
    predicate: Callable[[ExposureFeatures], bool]
    weight: int


def has_condition(condition: Condition) -> Callable[[Person], bool]:
    return lambda p: condition in p.conditions


def has_med_class(med_class: MedClass) -> Callable[[Person], bool]:
    return lambda p: any(med.drug_class is med_class for med in p.medications)


# Spec 8.2, transcribed row for row. Diffable against the table during review.
VULNERABILITY_RULES: tuple[VulnerabilityRule, ...] = (
    VulnerabilityRule(ReasonCode.AGE_85_PLUS, lambda p: p.age_band is AgeBand.B85_PLUS, 3),
    VulnerabilityRule(ReasonCode.AGE_75_84, lambda p: p.age_band is AgeBand.B75_84, 2),
    VulnerabilityRule(ReasonCode.LIVES_ALONE, lambda p: p.lives_alone, 2),
    VulnerabilityRule(ReasonCode.DEMENTIA, has_condition(Condition.DEMENTIA), 2),
    VulnerabilityRule(ReasonCode.CARDIOVASCULAR, has_condition(Condition.CARDIOVASCULAR), 2),
    VulnerabilityRule(ReasonCode.RENAL, has_condition(Condition.RENAL), 2),
    VulnerabilityRule(ReasonCode.RESPIRATORY, has_condition(Condition.RESPIRATORY), 1),
    VulnerabilityRule(ReasonCode.MOBILITY_LIMITED, lambda p: p.mobility_limited, 1),
    VulnerabilityRule(ReasonCode.MED_LITHIUM, has_med_class(MedClass.LITHIUM), 3),
    VulnerabilityRule(ReasonCode.MED_DIURETIC, has_med_class(MedClass.DIURETIC), 2),
    VulnerabilityRule(ReasonCode.MED_ANTICHOLINERGIC, has_med_class(MedClass.ANTICHOLINERGIC), 2),
    VulnerabilityRule(ReasonCode.MED_ANTIPSYCHOTIC, has_med_class(MedClass.ANTIPSYCHOTIC), 2),
    VulnerabilityRule(ReasonCode.MED_ACE_ARB, has_med_class(MedClass.ACE_ARB), 1),
    VulnerabilityRule(ReasonCode.MED_BETA_BLOCKER, has_med_class(MedClass.BETA_BLOCKER), 1),
    VulnerabilityRule(ReasonCode.MED_SSRI, has_med_class(MedClass.SSRI), 1),
)

# Spec 8.1. SUSTAINED_SPELL's "peak >= 24" is read as peak_apparent — the reading
# that reproduces the section 8.6 worked example (29 degrees apparent).
EXPOSURE_RULES: tuple[ExposureRule, ...] = (
    ExposureRule(ReasonCode.NIGHT_NO_RECOVERY, lambda e: e.overnight_min >= 20, 3),
    ExposureRule(ReasonCode.BEDROOM_UNSAFE, lambda e: e.indoor_night_est >= 26, 3),
    ExposureRule(ReasonCode.BEDROOM_WARM, lambda e: 24 <= e.indoor_night_est < 26, 1),
    ExposureRule(ReasonCode.PEAK_HEAT, lambda e: e.peak_apparent >= 30, 2),
    ExposureRule(
        ReasonCode.SUSTAINED_SPELL, lambda e: e.spell_day >= 3 and e.peak_apparent >= 24, 2
    ),
    ExposureRule(ReasonCode.INDOOR_BELOW_18, lambda e: 16 <= e.indoor_day_est < 18, 2),
    ExposureRule(ReasonCode.INDOOR_BELOW_16, lambda e: 12 <= e.indoor_day_est < 16, 3),
    ExposureRule(ReasonCode.INDOOR_BELOW_12, lambda e: e.indoor_day_est < 12, 4),
)
```

```python
# packages/core/src/core/vulnerability.py
from contracts import Person, VulnerabilityProfile
from core.rules import VULNERABILITY_RULES, VulnerabilityRule


class VulnerabilityScorer:
    """L2. Deterministic: no I/O, no clock, every input arrives as an argument."""

    def __init__(self, rules: tuple[VulnerabilityRule, ...] = VULNERABILITY_RULES) -> None:
        self.rules = rules

    def profile(self, person: Person) -> VulnerabilityProfile:
        triggered = [rule for rule in self.rules if rule.predicate(person)]
        return VulnerabilityProfile(
            person_id=person.id,
            score=sum(rule.weight for rule in triggered),
            codes=tuple(rule.code for rule in triggered),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/test_vulnerability.py -v`
Expected: PASS, with Doris scoring exactly 10

- [ ] **Step 5: Commit**

```bash
git add packages/core tests/core
git commit -m "feat(core): L2 VulnerabilityScorer over a rule table"
```

---

## Task 6: L3 risk fusion

**Files:**
- Create: `packages/core/src/core/scoring.py`
- Test: `tests/core/test_scoring.py`

**Interfaces:**
- Consumes: `contracts.ExposureFeatures`, `contracts.VulnerabilityProfile`, `core.corpus.Corpus`, `core.rules.EXPOSURE_RULES`
- Produces: `RiskScorer(corpus: Corpus, exposure_rules=..., vulnerability_rules=...)` with `assess(exposure, vulnerability) -> Assessment` and `staticmethod tier_for(risk: float) -> Tier`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_scoring.py
from datetime import date

import pytest
from contracts import (
    AlertLevel,
    ExposureFeatures,
    ExposureSource,
    ReasonCode,
    Tier,
    VulnerabilityProfile,
)
from core.corpus import Corpus
from core.scoring import RiskScorer


@pytest.fixture(scope="module")
def scorer() -> RiskScorer:
    return RiskScorer(Corpus.load())


def exposure(**kw) -> ExposureFeatures:
    base = dict(
        date=date(2025, 7, 19),
        overnight_min=12.0,
        peak_apparent=18.0,
        peak_air=18.0,
        hours_above_26=0,
        indoor_night_est=19.0,
        indoor_day_est=21.0,
        spell_day=0,
        alert_level=AlertLevel.NOT_CHECKED,
        source=ExposureSource.FIXTURE,
    )
    return ExposureFeatures(**(base | kw))


def vuln(score: int) -> VulnerabilityProfile:
    return VulnerabilityProfile(person_id="p", score=score, codes=())


@pytest.mark.parametrize(
    "risk,expected",
    [
        (0.0, Tier.LOW),
        (1.9, Tier.LOW),
        (2.0, Tier.ELEVATED),
        (4.9, Tier.ELEVATED),
        (5.0, Tier.HIGH),
        (8.9, Tier.HIGH),
        (9.0, Tier.SEVERE),
        (30.0, Tier.SEVERE),
    ],
)
def test_tier_boundaries_per_spec_8_5(risk, expected):
    assert RiskScorer.tier_for(risk) is expected


def test_zero_exposure_returns_low_however_frail(scorer):
    """FR-18. The rule that stops frail people sitting permanently at Elevated."""
    a = scorer.assess(exposure(), vuln(score=30))
    assert a.exposure_score == 0
    assert a.tier is Tier.LOW
    assert a.risk_score == 0.0


def test_multiplier_is_one_plus_score_over_ten(scorer):
    a = scorer.assess(exposure(indoor_night_est=24.5), vuln(score=10))
    assert a.exposure_score == 1  # BEDROOM_WARM
    assert a.risk_score == pytest.approx(2.0)  # 1 * (1 + 10/10)


@pytest.mark.parametrize(
    "indoor_night,expected_code",
    [(26.5, ReasonCode.BEDROOM_UNSAFE), (24.5, ReasonCode.BEDROOM_WARM)],
)
def test_bedroom_codes_are_mutually_exclusive(scorer, indoor_night, expected_code):
    codes = {
        r.code for r in scorer.assess(exposure(indoor_night_est=indoor_night), vuln(0)).reasons
    }
    assert codes & {ReasonCode.BEDROOM_UNSAFE, ReasonCode.BEDROOM_WARM} == {expected_code}


def test_reasons_carry_text_from_the_corpus_and_weight_from_the_rules(scorer):
    a = scorer.assess(exposure(indoor_night_est=24.5), vuln(0))
    reason = next(r for r in a.reasons if r.code is ReasonCode.BEDROOM_WARM)
    assert reason.title and reason.explanation
    assert reason.weight == 1


def test_vulnerability_codes_appear_in_the_reasons_array(scorer):
    v = VulnerabilityProfile(person_id="p", score=3, codes=(ReasonCode.AGE_85_PLUS,))
    codes = {r.code for r in scorer.assess(exposure(indoor_night_est=24.5), v).reasons}
    assert ReasonCode.AGE_85_PLUS in codes


def test_assess_is_deterministic(scorer):
    e, v = exposure(indoor_night_est=24.5), vuln(10)
    assert scorer.assess(e, v) == scorer.assess(e, v)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.scoring'`

- [ ] **Step 3: Implement the scorer**

```python
# packages/core/src/core/scoring.py
from contracts import (
    Assessment,
    ExposureFeatures,
    Reason,
    ReasonCode,
    Tier,
    VulnerabilityProfile,
)
from core.corpus import Corpus
from core.rules import (
    EXPOSURE_RULES,
    VULNERABILITY_RULES,
    ExposureRule,
    VulnerabilityRule,
)


class RiskScorer:
    """L3 risk fusion.

    AC-1: no I/O, no database, no clock. The Corpus is injected at construction and
    holds text only — it never influences the score, so assess() stays deterministic
    over its arguments and replays identically against archived weather (AC-5).
    """

    THRESHOLDS: tuple[tuple[float, Tier], ...] = (
        (9.0, Tier.SEVERE),
        (5.0, Tier.HIGH),
        (2.0, Tier.ELEVATED),
    )

    def __init__(
        self,
        corpus: Corpus,
        exposure_rules: tuple[ExposureRule, ...] = EXPOSURE_RULES,
        vulnerability_rules: tuple[VulnerabilityRule, ...] = VULNERABILITY_RULES,
    ) -> None:
        self.corpus = corpus
        self.exposure_rules = exposure_rules
        self.weights: dict[ReasonCode, int] = {
            rule.code: rule.weight for rule in (*exposure_rules, *vulnerability_rules)
        }

    @staticmethod
    def tier_for(risk: float) -> Tier:
        for floor, tier in RiskScorer.THRESHOLDS:
            if risk >= floor:
                return tier
        return Tier.LOW

    def build_reasons(self, codes: list[ReasonCode]) -> tuple[Reason, ...]:
        return tuple(
            Reason(
                code=code,
                title=self.corpus.reasons[code].title,
                explanation=self.corpus.reasons[code].explanation,
                weight=self.weights[code],
            )
            for code in codes
        )

    def assess(self, exposure: ExposureFeatures, vulnerability: VulnerabilityProfile) -> Assessment:
        triggered = [rule for rule in self.exposure_rules if rule.predicate(exposure)]
        exposure_score = sum(rule.weight for rule in triggered)

        # FR-18: zero exposure is Low regardless of frailty. Vulnerability modifies
        # the effect of exposure; it is not itself a harm.
        risk = 0.0 if exposure_score == 0 else exposure_score * (1 + vulnerability.score / 10)

        codes = [rule.code for rule in triggered] + list(vulnerability.codes)
        return Assessment(
            tier=self.tier_for(risk),
            risk_score=risk,
            exposure_score=exposure_score,
            vulnerability_score=vulnerability.score,
            reasons=self.build_reasons(codes),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core -v`
Expected: PASS, all core tests

- [ ] **Step 5: Commit**

```bash
git add packages/core tests/core
git commit -m "feat(core): L3 RiskScorer, deterministic and table-driven"
```

---

## Task 7: PersonaLoader and the §8.6 worked-example gate

**Files:**
- Create: `packages/persons/pyproject.toml`, `packages/persons/src/persons/loader.py`, `data/personas/doris.yaml`, `tests/verification/test_worked_example.py`

**Interfaces:**
- Consumes: `core.scoring.RiskScorer`, `core.vulnerability.VulnerabilityScorer`
- Produces: `PersonaFile` pydantic schema, `PersonaLoader(directory: Path | None = None)` with `load() -> dict[str, Person]`

- [ ] **Step 1: Write the failing test**

```python
# tests/verification/test_worked_example.py
"""Spec section 8.6. A merge gate — it must never go red."""

from datetime import date

import pytest
from contracts import AlertLevel, ExposureFeatures, ExposureSource, ReasonCode, Tier
from core.corpus import Corpus
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer
from persons.loader import PersonaLoader

BEDFORD_19_JULY_2025 = ExposureFeatures(
    date=date(2025, 7, 19),
    overnight_min=17.0,
    peak_apparent=29.0,
    peak_air=29.0,
    hours_above_26=7,
    indoor_night_est=24.6,  # 0.6(17) + 0.4(29) + 2.8
    indoor_day_est=25.85,  # 0.3(17) + 0.55(29) + 2.8 + 2
    spell_day=3,
    alert_level=AlertLevel.NONE,  # no alert was issued — this is the point
    source=ExposureSource.ARCHIVE,
)


@pytest.fixture(scope="module")
def doris():
    return PersonaLoader().load()["doris"]


@pytest.fixture(scope="module")
def assessment(doris):
    return RiskScorer(Corpus.load()).assess(
        BEDFORD_19_JULY_2025, VulnerabilityScorer().profile(doris)
    )


def test_doris_scores_exactly_six_and_lands_high(assessment):
    assert assessment.exposure_score == 3
    assert assessment.vulnerability_score == 10
    assert assessment.risk_score == pytest.approx(6.0)
    assert assessment.tier is Tier.HIGH


def test_reason_set_is_exactly_the_spec_worked_example(assessment):
    assert {r.code for r in assessment.reasons} == {
        ReasonCode.BEDROOM_WARM,
        ReasonCode.SUSTAINED_SPELL,
        ReasonCode.AGE_85_PLUS,
        ReasonCode.LIVES_ALONE,
        ReasonCode.DEMENTIA,
        ReasonCode.MED_DIURETIC,
        ReasonCode.MED_ACE_ARB,
    }


def test_high_tier_reached_with_no_regional_alert_in_force(assessment):
    """The target behaviour: personal risk without a national alert."""
    assert BEDFORD_19_JULY_2025.alert_level is AlertLevel.NONE
    assert assessment.tier >= Tier.HIGH
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/verification/test_worked_example.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'persons'`

- [ ] **Step 3: Write the persona schema, loader and Doris**

```yaml
# data/personas/doris.yaml
id: doris
name: Doris
age_band: b85_plus
lives_alone: true
mobility_limited: false
conditions: [dementia]
medications:
  - drug_name: furosemide
    drug_class: diuretic
  - drug_name: ramipril
    drug_class: ace_arb
place:
  postcode: MK40 1AA
  dwelling_type: flat
  floor: 3
  aspect: south
  has_cooling: false
  heating_affordable: true
```

```python
# packages/persons/src/persons/loader.py
from pathlib import Path

import yaml
from contracts import AgeBand, Condition, Med, MedClass, Person
from pydantic import BaseModel, Field

PERSONAS_DIR = Path(__file__).resolve().parents[4] / "data" / "personas"


class MedFile(BaseModel):
    drug_name: str
    drug_class: MedClass


class PlaceFile(BaseModel):
    postcode: str
    dwelling_type: str
    floor: int = 0
    aspect: str = "south"
    has_cooling: bool = False
    heating_affordable: bool = True


class PersonaFile(BaseModel):
    """Schema for data/personas/*.yaml. Contributors edit YAML, never Python."""

    id: str
    name: str
    age_band: AgeBand
    lives_alone: bool
    mobility_limited: bool = False
    conditions: list[Condition] = Field(default_factory=list)
    medications: list[MedFile] = Field(default_factory=list)
    place: PlaceFile

    def to_person(self) -> Person:
        return Person(
            id=self.id,
            name=self.name,
            age_band=self.age_band,
            lives_alone=self.lives_alone,
            mobility_limited=self.mobility_limited,
            conditions=tuple(self.conditions),
            medications=tuple(Med(m.drug_name, m.drug_class) for m in self.medications),
        )


class PersonaLoader:
    """Discovers and validates persona files. A contribution surface: adding a
    persona is a new YAML file and no Python edit at all."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or PERSONAS_DIR
        self.cache: dict[str, Person] | None = None

    def load(self) -> dict[str, Person]:
        if self.cache is None:
            self.cache = {p.id: p for p in self.read_all()}
        return self.cache

    def read_all(self) -> list[Person]:
        people: list[Person] = []
        for path in sorted(self.directory.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text())
            try:
                people.append(PersonaFile(**raw).to_person())
            except Exception as exc:
                raise ValueError(f"{path.name} is not a valid persona: {exc}") from exc
        return people
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/verification/test_worked_example.py -v`
Expected: PASS, 3 tests. `risk_score` must be exactly 6.0.

- [ ] **Step 5: Commit**

```bash
git add data/personas packages/persons tests/verification
git commit -m "feat(persons): PersonaLoader, and the 8.6 worked example as a merge gate"
```

---

## Task 8: Data contribution surfaces — personas and geography

**Files:**
- Create: `data/personas/harold.yaml`, `data/personas/margaret.yaml`, `data/geography/bedford.yaml`, `packages/geography/src/geography/loader.py`
- Test: `tests/data/test_contribution_surfaces.py`

**Interfaces:**
- Consumes: `persons.loader.PersonaLoader`
- Produces: `Resource`, `Locality` dataclasses; `LocalityFile` schema; `GeographyLoader(directory: Path | None = None)` with `load() -> dict[str, Locality]`

This task exists so adding a persona or a locality requires **no Python**. Its tests are the contract keeping that true.

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_contribution_surfaces.py
"""Guards the two data contribution surfaces."""

import pytest
from contracts import Tier
from core.corpus import Corpus
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer
from geography.loader import GEOGRAPHY_DIR, GeographyLoader
from persons.loader import PERSONAS_DIR, PersonaLoader

from tests.verification.test_worked_example import BEDFORD_19_JULY_2025


@pytest.fixture(scope="module")
def scorer() -> RiskScorer:
    return RiskScorer(Corpus.load())


@pytest.fixture(scope="module")
def people() -> dict:
    return PersonaLoader().load()


def test_every_persona_file_is_valid_and_scorable(scorer, people):
    assert len(people) == len(list(PERSONAS_DIR.glob("*.yaml")))
    for pid, person in people.items():
        a = scorer.assess(BEDFORD_19_JULY_2025, VulnerabilityScorer().profile(person))
        assert isinstance(a.tier, Tier), f"{pid} did not produce a tier"


def test_personas_discriminate_under_identical_conditions(scorer, people):
    """Spec section 13: three personas, same conditions, at least two distinct tiers."""
    assert len(people) >= 3, "need at least three personas to test discrimination"
    v = VulnerabilityScorer()
    tiers = {scorer.assess(BEDFORD_19_JULY_2025, v.profile(p)).tier for p in people.values()}
    assert len(tiers) >= 2, f"all personas returned the same tier: {tiers}"


def test_every_geography_file_is_valid():
    localities = GeographyLoader().load()
    assert len(localities) == len(list(GEOGRAPHY_DIR.glob("*.yaml")))
    for name, locality in localities.items():
        assert locality.resources, f"{name} declares no resources"
        for r in locality.resources:
            assert -11 <= r.lon <= 2 and 49 <= r.lat <= 61, f"{r.name} is not in the UK"


def test_invalid_persona_names_the_file_and_the_field(tmp_path):
    (tmp_path / "broken.yaml").write_text("id: broken\nname: B\nage_band: not_a_band\n")
    with pytest.raises(ValueError, match="broken.yaml"):
        PersonaLoader(tmp_path).load()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/data -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'geography'`

- [ ] **Step 3: Add two more personas and the geography loader**

`data/personas/harold.yaml` — 76, lives with spouse, cardiovascular, bisoprolol → scores 2+2+1 = 5.
`data/personas/margaret.yaml` — 68, lives alone, no conditions, no medications → scores 2.

```python
# packages/geography/src/geography/loader.py
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

GEOGRAPHY_DIR = Path(__file__).resolve().parents[4] / "data" / "geography"


@dataclass(frozen=True, slots=True)
class Resource:
    id: str
    type: str  # cool_space | pharmacy | warm_bank | council_welfare
    name: str
    lat: float
    lon: float
    opening_hours: str
    area_code: str


@dataclass(frozen=True, slots=True)
class Locality:
    name: str
    region: str
    admin_district: str
    wards: tuple[str, ...]
    resources: tuple[Resource, ...]


class ResourceFile(BaseModel):
    id: str
    type: str
    name: str
    lat: float
    lon: float
    opening_hours: str = "unknown"
    area_code: str


class LocalityFile(BaseModel):
    """Schema for data/geography/*.yaml. Contributors edit YAML, never Python."""

    name: str
    region: str
    admin_district: str
    wards: list[str] = Field(default_factory=list)
    resources: list[ResourceFile] = Field(default_factory=list)

    def to_locality(self) -> Locality:
        return Locality(
            name=self.name,
            region=self.region,
            admin_district=self.admin_district,
            wards=tuple(self.wards),
            resources=tuple(Resource(**r.model_dump()) for r in self.resources),
        )


class GeographyLoader:
    """Discovers and validates locality files. Adding a locality is a new YAML file."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or GEOGRAPHY_DIR
        self.cache: dict[str, Locality] | None = None

    def load(self) -> dict[str, Locality]:
        if self.cache is None:
            self.cache = {loc.name: loc for loc in self.read_all()}
        return self.cache

    def read_all(self) -> list[Locality]:
        localities: list[Locality] = []
        for path in sorted(self.directory.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text())
            try:
                localities.append(LocalityFile(**raw).to_locality())
            except Exception as exc:
                raise ValueError(f"{path.name} is not a valid locality: {exc}") from exc
        return localities
```

`data/geography/bedford.yaml`:

```yaml
name: Bedford
region: East of England
admin_district: Bedford
wards: [Castle, De Parys, Harpur, Kingsbrook, Queens Park]
resources:
  - id: bed-lib-01
    type: cool_space
    name: Bedford Central Library
    lat: 52.1364
    lon: -0.4669
    opening_hours: "Mon-Sat 09:00-17:00"
    area_code: E07000032
  - id: bed-pharm-01
    type: pharmacy
    name: High Street Pharmacy
    lat: 52.1358
    lon: -0.4681
    opening_hours: "Mon-Fri 09:00-18:00"
    area_code: E07000032
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/data -v`
Expected: PASS. Discrimination passes because Doris/Harold/Margaret score 10/5/2.

- [ ] **Step 5: Commit**

```bash
git add data packages/geography tests/data
git commit -m "feat(data): persona and geography contribution surfaces, schema-validated"
```

---

## Task 9: IndoorModel and ExposureNormaliser

**Files:**
- Create: `packages/exposure/src/exposure/indoor.py`, `packages/exposure/src/exposure/normalise.py`
- Test: `tests/exposure/test_indoor.py`

**Interfaces:**
- Consumes: `contracts.ExposureFeatures`, `contracts.SelfReport`
- Produces: `IndoorModel` with `night(outdoor_night_min, outdoor_day_max, dwelling_offset) -> float`, `day(...) -> float`, `apply_self_report(features, report) -> ExposureFeatures`; `ExposureNormaliser` with `overnight_minimum(hourly_temps) -> float`, `spell_day(daily_peaks, threshold) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/exposure/test_indoor.py
from datetime import date

import pytest
from contracts import (
    AlertLevel,
    DateRange,
    ExposureFeatures,
    ExposureSource,
    SelfReport,
)
from exposure.indoor import IndoorModel
from exposure.normalise import ExposureNormaliser

BEDFORD = ExposureFeatures(
    date=date(2025, 7, 19),
    overnight_min=17.0,
    peak_apparent=29.0,
    peak_air=29.0,
    hours_above_26=7,
    indoor_night_est=24.6,
    indoor_day_est=25.85,
    spell_day=3,
    alert_level=AlertLevel.NONE,
    source=ExposureSource.ARCHIVE,
)
WINDOW = DateRange(date(2025, 7, 19), date(2025, 7, 20))


@pytest.fixture(scope="module")
def model() -> IndoorModel:
    return IndoorModel()


@pytest.fixture(scope="module")
def normaliser() -> ExposureNormaliser:
    return ExposureNormaliser()


def test_indoor_night_matches_the_spec_8_6_worked_example(model):
    assert model.night(17.0, 29.0, 2.8) == pytest.approx(24.6)


def test_indoor_day_matches_fr_11(model):
    assert model.day(17.0, 29.0, 2.8) == pytest.approx(25.85)


def test_overnight_minimum_uses_the_2200_to_0700_window_only(normaliser):
    """FR-07. The 15:00 low must be ignored; only 22:00-07:00 counts."""
    hourly = {h: 25.0 for h in range(24)}
    hourly[15] = 5.0  # decoy, outside the window
    hourly[3] = 18.0  # the real overnight minimum
    assert normaliser.overnight_minimum(hourly) == 18.0


def test_overnight_minimum_raises_when_the_window_is_empty(normaliser):
    with pytest.raises(ValueError, match="22:00"):
        normaliser.overnight_minimum({12: 20.0})


@pytest.mark.parametrize(
    "peaks,expected",
    [([25.0, 25.0, 25.0], 3), ([25.0, 20.0, 25.0], 1), ([], 0), ([20.0, 20.0], 0)],
)
def test_spell_day_counts_consecutive_days_only(normaliser, peaks, expected):
    """FR-09. A break in the spell resets the count."""
    assert normaliser.spell_day(peaks, threshold=24.0) == expected


def test_self_report_of_a_hot_bedroom_raises_the_indoor_estimate(model):
    """Spec section 6: a cheap partial substitute for the sensor in v0.3."""
    after = model.apply_self_report(
        BEDFORD,
        SelfReport(person_id="doris", window=WINDOW, answered=True, bedroom_feels_hot=True),
    )
    assert after.indoor_night_est > BEDFORD.indoor_night_est
    assert after.source is ExposureSource.SELF_REPORT
    assert BEDFORD.indoor_night_est == 24.6, "input must not be mutated"


def test_self_report_correction_is_bounded(model):
    """An unbounded correction would let one answer dominate the model."""
    after = model.apply_self_report(
        BEDFORD,
        SelfReport(person_id="d", window=WINDOW, answered=True, bedroom_feels_hot=True),
    )
    assert after.indoor_night_est - BEDFORD.indoor_night_est <= 2.0


@pytest.mark.parametrize(
    "report",
    [
        SelfReport(person_id="d", window=WINDOW, answered=False),
        SelfReport(person_id="d", window=WINDOW, answered=True, bedroom_feels_hot=False),
        SelfReport(person_id="d", window=WINDOW, answered=True, bedroom_feels_hot=None),
    ],
    ids=["no_answer", "said_no", "did_not_say"],
)
def test_exposure_untouched_unless_the_person_said_yes(model, report):
    assert model.apply_self_report(BEDFORD, report) == BEDFORD
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/exposure -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'exposure'`

- [ ] **Step 3: Implement**

```python
# packages/exposure/src/exposure/indoor.py
from dataclasses import replace

from contracts import ExposureFeatures, ExposureSource, SelfReport


class IndoorModel:
    """FR-11. Modelled, not measured — label as modelled wherever displayed (SC-5).

    The dominant error term at plus or minus 3 to 5 degrees. A bedroom sensor
    replaces this in v0.3; apply_self_report closes part of the gap today.
    """

    SELF_REPORT_HOT_OFFSET = 1.5
    """Bounded. A subjective answer nudges the estimate; it never replaces it."""

    def __init__(self, self_report_offset: float = SELF_REPORT_HOT_OFFSET) -> None:
        self.self_report_offset = self_report_offset

    @staticmethod
    def night(outdoor_night_min: float, outdoor_day_max: float, dwelling_offset: float) -> float:
        return 0.6 * outdoor_night_min + 0.4 * outdoor_day_max + dwelling_offset

    @staticmethod
    def day(outdoor_night_min: float, outdoor_day_max: float, dwelling_offset: float) -> float:
        return 0.3 * outdoor_night_min + 0.55 * outdoor_day_max + dwelling_offset + 2

    def apply_self_report(self, features: ExposureFeatures, report: SelfReport) -> ExposureFeatures:
        """Correct the modelled estimate with what the person actually said.

        Red flags and no-answer are NOT handled here — they escalate at L4 and
        never enter risk fusion (spec section 6).
        """
        if not report.answered or report.bedroom_feels_hot is not True:
            return features
        return replace(
            features,
            indoor_night_est=features.indoor_night_est + self.self_report_offset,
            source=ExposureSource.SELF_REPORT,
        )
```

```python
# packages/exposure/src/exposure/normalise.py
from collections.abc import Sequence


class ExposureNormaliser:
    """Turns an hourly forecast into the features that predict harm (FR-07 to FR-09),
    rather than the ones the forecast happens to hand you."""

    NIGHT_HOURS: tuple[int, ...] = (22, 23, 0, 1, 2, 3, 4, 5, 6, 7)

    @classmethod
    def overnight_minimum(cls, hourly_temps: dict[int, float]) -> float:
        """FR-07. Minimum air temperature between 22:00 and 07:00."""
        window = [hourly_temps[h] for h in cls.NIGHT_HOURS if h in hourly_temps]
        if not window:
            raise ValueError("no hourly temperatures in the 22:00-07:00 window")
        return min(window)

    @staticmethod
    def spell_day(daily_peaks: Sequence[float], threshold: float) -> int:
        """FR-09. Consecutive days meeting the episode threshold, counting back."""
        count = 0
        for peak in reversed(daily_peaks):
            if peak < threshold:
                break
            count += 1
        return count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/exposure -v`
Expected: PASS, 13 tests

- [ ] **Step 5: Commit**

```bash
git add packages/exposure tests/exposure
git commit -m "feat(exposure): IndoorModel, ExposureNormaliser and self-report correction"
```

---

## Task 10: Predictor seam with a green deterministic baseline

**Files:**
- Create: `packages/predictors/src/predictors/base.py`, `heatwave.py`, `cold_lag.py`, `backtest.py`
- Test: `tests/predictors/test_heatwave.py`

**Interfaces:**
- Consumes: nothing from other tracks
- Produces: `EpisodeForecast` dataclass; `Predictor` Protocol with `forecast(daily_peaks: Sequence[float], horizon_days: int) -> EpisodeForecast`; `ThresholdHeatwave` (green), `EnsembleHeatwave` (stub, Track B), `ColdLagTracker` (stub), `SeasonBacktest` (stub)

- [ ] **Step 1: Write the failing test**

```python
# tests/predictors/test_heatwave.py
import pytest
from predictors.base import Predictor
from predictors.heatwave import EPISODE_THRESHOLD, EnsembleHeatwave, ThresholdHeatwave


@pytest.fixture(scope="module")
def predictor() -> ThresholdHeatwave:
    return ThresholdHeatwave()


def test_threshold_predictor_satisfies_the_protocol(predictor):
    assert isinstance(predictor, Predictor)


def test_onset_is_certain_when_every_day_clears_the_threshold(predictor):
    f = predictor.forecast([30.0, 30.0, 30.0], horizon_days=3)
    assert f.p_onset == 1.0
    assert f.expected_duration_days == 3
    assert f.ensemble_spread == 0.0  # deterministic: no disagreement to report


def test_no_onset_when_nothing_clears_the_threshold(predictor):
    f = predictor.forecast([15.0, 16.0, 15.0], horizon_days=3)
    assert f.p_onset == 0.0
    assert f.lead_time_hours == 0


def test_lead_time_counts_hours_to_the_first_qualifying_day(predictor):
    f = predictor.forecast([15.0, 15.0, 15.0, 30.0], horizon_days=4)
    assert f.p_onset == 1.0
    assert f.lead_time_hours == 72  # three clear days ahead of onset


@pytest.mark.parametrize("horizon", [1, 7, 14])
def test_forecast_never_reads_beyond_its_horizon(predictor, horizon):
    f = predictor.forecast([30.0] * 20, horizon_days=horizon)
    assert f.horizon_days == horizon
    assert f.expected_duration_days <= horizon


def test_empty_forecast_does_not_raise(predictor):
    f = predictor.forecast([], horizon_days=7)
    assert f.p_onset == 0.0
    assert f.expected_peak == 0.0


def test_episode_threshold_matches_the_ukhsa_definition():
    assert EPISODE_THRESHOLD == 24.0


def test_ensemble_predictor_is_an_unclaimed_stub():
    with pytest.raises(NotImplementedError, match="Track B"):
        EnsembleHeatwave().forecast([30.0], horizon_days=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/predictors -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'predictors'`

- [ ] **Step 3: Implement the seam and the baseline**

```python
# packages/predictors/src/predictors/base.py
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class EpisodeForecast:
    horizon_days: int
    p_onset: float  # P(episode threshold met)
    expected_peak: float
    expected_duration_days: int
    ensemble_spread: float  # model disagreement, i.e. confidence
    lead_time_hours: int  # the number a council acts on


@runtime_checkable
class Predictor(Protocol):
    def forecast(self, daily_peaks: Sequence[float], horizon_days: int) -> EpisodeForecast: ...
```

```python
# packages/predictors/src/predictors/heatwave.py
from collections.abc import Sequence

from predictors.base import EpisodeForecast

EPISODE_THRESHOLD = 24.0
"""UKHSA episode definition, matching the EPISODES data in the national view."""


class ThresholdHeatwave:
    """Deterministic baseline. Ships green so the chain works from hour one.

    EnsembleHeatwave upgrades this in place behind the same Protocol, which is the
    mitigation for the largest schedule risk in the build (spec section 13).
    """

    def __init__(self, threshold: float = EPISODE_THRESHOLD) -> None:
        self.threshold = threshold

    def forecast(self, daily_peaks: Sequence[float], horizon_days: int) -> EpisodeForecast:
        window = list(daily_peaks[:horizon_days])
        qualifying = [i for i, peak in enumerate(window) if peak >= self.threshold]
        if not qualifying:
            return EpisodeForecast(
                horizon_days=horizon_days,
                p_onset=0.0,
                expected_peak=max(window, default=0.0),
                expected_duration_days=0,
                ensemble_spread=0.0,
                lead_time_hours=0,
            )
        return EpisodeForecast(
            horizon_days=horizon_days,
            p_onset=1.0,
            expected_peak=max(window),
            expected_duration_days=len(qualifying),
            ensemble_spread=0.0,
            lead_time_hours=qualifying[0] * 24,
        )


class EnsembleHeatwave:
    """Track B. P(onset) from the fraction of ICON/GFS/ECMWF members over threshold."""

    def forecast(self, daily_peaks: Sequence[float], horizon_days: int) -> EpisodeForecast:
        raise NotImplementedError(
            "Track B owns this. Fetch the Open-Meteo ensemble endpoint, compute "
            "p_onset as the member fraction clearing EPISODE_THRESHOLD, and report "
            "ensemble_spread as the inter-member standard deviation of peak. "
            "SC-7: trigger preparation at a deliberately low p_onset and document "
            "the false-positive rate from the backtest."
        )
```

```python
# packages/predictors/src/predictors/cold_lag.py
class ColdLagTracker:
    """Track B. Spec section 12: cold mortality lags the spell by 1 to 2 weeks, so
    an alerting-shaped design mistimes it. This needs tracking, not alerting."""

    def track(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track B owns this. Deferred to v0.4 — spec section 12.")
```

```python
# packages/predictors/src/predictors/backtest.py
class SeasonBacktest:
    """Track B. Replay summer 2025 via the Open-Meteo archive and report whether
    Episode 4 (17-19 July, no alert issued, 146 deaths) would have been flagged at
    72 hours or more of lead time. The strongest falsifiable claim in the project."""

    def run(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track B owns this. See spec section 5.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/predictors -v`
Expected: PASS, 10 tests

- [ ] **Step 5: Commit**

```bash
git add packages/predictors tests/predictors
git commit -m "feat(predictors): Predictor seam with green deterministic baseline"
```

---

## Task 11: Voice check-in — closed utterance set

**Files:**
- Create: `packages/checkin/src/checkin/script.py`, `packages/checkin/src/checkin/voice.py`
- Test: `tests/verification/test_voice_utterances.py`, `tests/checkin/test_script.py`

**Interfaces:**
- Consumes: `core.corpus.Corpus`, `contracts.Assessment`
- Produces: `CheckinScript(corpus: Corpus)` with `all_utterances -> frozenset[str]` and `utterances_for(assessment: Assessment) -> tuple[str, ...]`; `VoiceChannel` Protocol; `ConsoleVoice(replies: list[str] | None)` with `say(utterance) -> None`, `ask(question) -> bool | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/verification/test_voice_utterances.py
"""Merge gate. The voice agent selects from the corpus — it never composes."""

import re

import pytest
from checkin.script import CheckinScript
from contracts import Assessment, Reason, ReasonCode, Tier
from core.corpus import Corpus

FORBIDDEN = re.compile(r"\b(stop|reduce|skip|halt|delay|alter)\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def script() -> CheckinScript:
    return CheckinScript(Corpus.load())


def test_every_possible_utterance_is_sourced_from_the_action_corpus(script):
    corpus_text = {row.text for row in script.corpus.actions}
    unsourced = script.all_utterances - corpus_text
    assert not unsourced, f"utterances not traceable to the corpus: {unsourced}"


def test_no_utterance_can_advise_altering_a_prescription(script):
    """SC-1, enforced on the voice surface specifically."""
    offending = [u for u in script.all_utterances if FORBIDDEN.search(u)]
    assert not offending, f"SC-1 violation in voice utterances: {offending}"


def test_selected_utterances_are_a_subset_of_the_closed_set(script):
    a = Assessment(
        tier=Tier.HIGH,
        risk_score=6.0,
        exposure_score=3,
        vulnerability_score=10,
        reasons=(Reason(ReasonCode.MED_DIURETIC, "t", "e", 2),),
    )
    assert set(script.utterances_for(a)) <= script.all_utterances
```

```python
# tests/checkin/test_script.py
import pytest
from checkin.script import CheckinScript
from checkin.voice import ConsoleVoice
from contracts import Assessment, Reason, ReasonCode, Tier
from core.corpus import Corpus


@pytest.fixture(scope="module")
def script() -> CheckinScript:
    return CheckinScript(Corpus.load())


def assessment(tier: Tier, *codes: ReasonCode) -> Assessment:
    return Assessment(
        tier=tier,
        risk_score=6.0,
        exposure_score=3,
        vulnerability_score=10,
        reasons=tuple(Reason(c, "t", "e", 1) for c in codes),
    )


def test_low_tier_produces_no_call(script):
    assert script.utterances_for(assessment(Tier.LOW, ReasonCode.MED_DIURETIC)) == ()


def test_no_utterance_repeats_within_one_call(script):
    said = script.utterances_for(
        assessment(Tier.HIGH, ReasonCode.MED_DIURETIC, ReasonCode.MED_LITHIUM)
    )
    assert len(said) == len(set(said))


def test_rows_above_the_callers_tier_are_not_read(script):
    """A row marked tier_min=high must not surface on an Elevated call."""
    elevated = script.utterances_for(assessment(Tier.ELEVATED, ReasonCode.MED_LITHIUM))
    high = script.utterances_for(assessment(Tier.HIGH, ReasonCode.MED_LITHIUM))
    assert set(elevated) <= set(high)


@pytest.mark.parametrize(
    "reply,expected",
    [("yes", True), ("Yes", True), ("no", False), ("mmm", None), ("", None)],
)
def test_unrecognised_reply_is_none_never_free_text(reply, expected):
    assert ConsoleVoice(replies=[reply]).ask("Is your bedroom warm?") is expected


def test_console_voice_records_a_transcript():
    voice = ConsoleVoice(replies=["yes"])
    voice.say("Open the windows after sunset.")
    voice.ask("Is your bedroom warm?")
    assert len(voice.transcript) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/checkin tests/verification/test_voice_utterances.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'checkin'`

- [ ] **Step 3: Implement selection, not generation**

```python
# packages/checkin/src/checkin/script.py
from contracts import Assessment, Tier
from core.corpus import Corpus


class CheckinScript:
    """Chooses which corpus rows the caller hears.

    The governing constraint of spec section 6: this selects utterances, it never
    composes them. Every line is a row that already passed the SC-1 safety grep, so
    the agent cannot say something novel about a medicine because it cannot compose
    a novel sentence at all.
    """

    TIER_BY_NAME: dict[str, Tier] = {
        "low": Tier.LOW,
        "elevated": Tier.ELEVATED,
        "high": Tier.HIGH,
        "severe": Tier.SEVERE,
    }

    def __init__(self, corpus: Corpus) -> None:
        self.corpus = corpus

    @property
    def all_utterances(self) -> frozenset[str]:
        """The closed set. The agent can say these strings and nothing else."""
        return frozenset(row.text for row in self.corpus.actions)

    def utterances_for(self, assessment: Assessment) -> tuple[str, ...]:
        if assessment.tier is Tier.LOW:
            return ()
        codes = {reason.code for reason in assessment.reasons}
        rows = sorted(
            (
                row
                for row in self.corpus.actions
                if row.reason_code in codes and assessment.tier >= self.TIER_BY_NAME[row.tier_min]
            ),
            key=lambda row: row.ordering,
        )
        seen: set[str] = set()
        chosen: list[str] = []
        for row in rows:
            if row.text not in seen:
                seen.add(row.text)
                chosen.append(row.text)
        return tuple(chosen)
```

```python
# packages/checkin/src/checkin/voice.py
from typing import Protocol, runtime_checkable


@runtime_checkable
class VoiceChannel(Protocol):
    def say(self, utterance: str) -> None: ...
    def ask(self, question: str) -> bool | None: ...


class ConsoleVoice:
    """Prints the transcript and reads replies. Ships green so the whole flow is
    demoable with no telephony account, no phone number and no per-minute cost."""

    YES = frozenset({"yes", "yeah", "yep", "y"})
    NO = frozenset({"no", "nope", "n"})

    def __init__(self, replies: list[str] | None = None) -> None:
        self.replies = list(replies or [])
        self.transcript: list[str] = []

    def say(self, utterance: str) -> None:
        self.transcript.append(utterance)
        print(f"  [voice] {utterance}")

    def ask(self, question: str) -> bool | None:
        self.transcript.append(question)
        reply = self.replies.pop(0) if self.replies else input(f"  [voice] {question} ")
        normalised = reply.strip().lower()
        if normalised in self.YES:
            return True
        if normalised in self.NO:
            return False
        return None  # unrecognised is no-answer, never free text to interpret
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/checkin tests/verification -v`
Expected: PASS. If the sourcing test fails, the agent has gained a string it cannot justify — that is the gate working.

- [ ] **Step 5: Commit**

```bash
git add packages/checkin tests/checkin tests/verification
git commit -m "feat(checkin): closed-utterance CheckinScript with ConsoleVoice"
```

---

## Task 12: Resource allocation algorithms

**Files:**
- Create: `packages/allocation/src/allocation/distance.py`, `models.py`, `plans.py`
- Test: `tests/allocation/test_distance.py`, `tests/allocation/test_plans.py`

**Interfaces:**
- Consumes: `contracts.Assessment`, `geography.loader.Resource`
- Produces: `haversine_km(lat1, lon1, lat2, lon2) -> float`; `Candidate`, `Visit`, `AllocationPlan`, `UncoveredPerson`, `CoverageReport`, `SitingOption`; `AllocationEngine(isolation_factor=2.0, mobility_factor=1.2, no_cooling_factor=1.15)` with `rank_visits(candidates, capacity)`, `coverage_gap(candidates, resources, radius_km, min_tier)`, `siting_delta(report, sites, radius_km)`

These ship **green**. The ranking algorithm is the intellectual content of the layer, so it belongs where the whole team can see it. Track B owns tuning the weights afterwards — which is why they are constructor parameters rather than module constants.

- [ ] **Step 1: Write the failing test**

```python
# tests/allocation/test_distance.py
import pytest
from allocation.distance import haversine_km


def test_distance_between_bedford_library_and_high_street_pharmacy():
    assert 0.05 < haversine_km(52.1364, -0.4669, 52.1358, -0.4681) < 0.2


def test_distance_to_self_is_zero():
    assert haversine_km(52.1364, -0.4669, 52.1364, -0.4669) == pytest.approx(0.0)


def test_london_to_bedford_is_about_seventy_kilometres():
    assert haversine_km(51.5074, -0.1278, 52.1364, -0.4669) == pytest.approx(73, abs=4)
```

```python
# tests/allocation/test_plans.py
import pytest
from allocation.models import Candidate
from allocation.plans import AllocationEngine
from contracts import Assessment, Tier
from geography.loader import Resource


@pytest.fixture(scope="module")
def engine() -> AllocationEngine:
    return AllocationEngine()


def candidate(
    pid: str,
    tier: Tier,
    *,
    alone: bool = True,
    mobility_limited: bool = False,
    lat: float = 52.13,
    lon: float = -0.46,
    has_cooling: bool = False,
) -> Candidate:
    return Candidate(
        person_id=pid,
        assessment=Assessment(
            tier=tier,
            risk_score=float(tier) * 3,
            exposure_score=3,
            vulnerability_score=10,
            reasons=(),
        ),
        lives_alone=alone,
        mobility_limited=mobility_limited,
        lat=lat,
        lon=lon,
        has_cooling=has_cooling,
    )


def cool_space(rid: str, lat: float, lon: float) -> Resource:
    return Resource(
        id=rid,
        type="cool_space",
        name=rid,
        lat=lat,
        lon=lon,
        opening_hours="09:00-17:00",
        area_code="E07000032",
    )


def test_higher_tier_outranks_lower_tier_all_else_equal(engine):
    plan = engine.rank_visits(
        [candidate("low", Tier.ELEVATED), candidate("high", Tier.SEVERE)], capacity=2
    )
    assert [v.person_id for v in plan.visits] == ["high", "low"]


def test_isolation_can_outrank_a_higher_tier(engine):
    """The design claim: optimise harm averted per visit, not risk observed.

    Severe-supported scores 5.0 x 1.15 = 5.75. High-alone scores
    3.0 x 2.0 x 1.15 = 6.90. The visit is worth more to the person nobody is watching.
    """
    plan = engine.rank_visits(
        [
            candidate("severe_supported", Tier.SEVERE, alone=False),
            candidate("high_alone", Tier.HIGH, alone=True),
        ],
        capacity=2,
    )
    assert plan.visits[0].person_id == "high_alone"


def test_lowering_the_isolation_factor_reverts_to_ranking_on_tier():
    """Guards the policy decision: below the Severe/High ratio, tier dominates."""
    plan = AllocationEngine(isolation_factor=1.0).rank_visits(
        [
            candidate("severe_supported", Tier.SEVERE, alone=False),
            candidate("high_alone", Tier.HIGH, alone=True),
        ],
        capacity=2,
    )
    assert plan.visits[0].person_id == "severe_supported"


def test_capacity_is_respected_and_the_remainder_is_reported(engine):
    plan = engine.rank_visits([candidate(f"p{i}", Tier.HIGH) for i in range(10)], capacity=4)
    assert len(plan.visits) == 4
    assert plan.unvisited == 6


def test_low_tier_is_never_scheduled_even_with_spare_capacity(engine):
    plan = engine.rank_visits([candidate("a", Tier.LOW), candidate("b", Tier.LOW)], capacity=10)
    assert plan.visits == ()
    assert plan.unvisited == 0


def test_every_visit_carries_its_justification(engine):
    plan = engine.rank_visits([candidate("a", Tier.SEVERE, mobility_limited=True)], capacity=1)
    assert "severe" in plan.visits[0].rationale
    assert "mobility limited" in plan.visits[0].rationale


def test_ranking_is_stable_for_equal_priorities(engine):
    plan = engine.rank_visits(
        [candidate("zoe", Tier.HIGH), candidate("amy", Tier.HIGH)], capacity=2
    )
    assert [v.person_id for v in plan.visits] == ["amy", "zoe"]


def test_coverage_gap_finds_people_beyond_the_radius(engine):
    report = engine.coverage_gap(
        [
            candidate("near", Tier.SEVERE, lat=52.1364, lon=-0.4669),
            candidate("far", Tier.SEVERE, lat=52.5000, lon=-0.4669),
        ],
        [cool_space("lib", 52.1364, -0.4669)],
        radius_km=1.0,
        min_tier=Tier.HIGH,
    )
    assert {u.person_id for u in report.uncovered} == {"far"}
    assert report.covered_count == 1


def test_coverage_gap_ignores_people_below_the_minimum_tier(engine):
    report = engine.coverage_gap(
        [candidate("mild", Tier.ELEVATED, lat=52.5, lon=-0.46)],
        [cool_space("lib", 52.1364, -0.4669)],
        radius_km=1.0,
        min_tier=Tier.HIGH,
    )
    assert report.uncovered == ()
    assert report.considered == 0


def test_person_with_cooling_at_home_is_already_covered(engine):
    report = engine.coverage_gap(
        [candidate("cooled", Tier.SEVERE, lat=52.5, lon=-0.46, has_cooling=True)],
        [cool_space("lib", 52.1364, -0.4669)],
        radius_km=1.0,
        min_tier=Tier.HIGH,
    )
    assert report.uncovered == ()


def test_uncovered_person_reports_no_nearest_when_no_resources_exist(engine):
    report = engine.coverage_gap(
        [candidate("alone", Tier.SEVERE)], [], radius_km=1.0, min_tier=Tier.HIGH
    )
    assert report.uncovered[0].nearest_km is None


def test_siting_delta_ranks_candidate_sites_by_people_newly_covered(engine):
    people = [candidate(f"p{i}", Tier.SEVERE, lat=52.50, lon=-0.46) for i in range(3)]
    people.append(candidate("lonely", Tier.SEVERE, lat=53.00, lon=-0.46))
    report = engine.coverage_gap(people, [], radius_km=1.0, min_tier=Tier.HIGH)

    options = engine.siting_delta(
        report,
        [cool_space("cluster", 52.50, -0.46), cool_space("outlier", 53.00, -0.46)],
        radius_km=1.0,
    )
    assert [o.resource_id for o in options] == ["cluster", "outlier"]
    assert options[0].newly_covered == 3
    assert options[1].newly_covered == 1


def test_siting_delta_with_no_uncovered_people_returns_zero_gain(engine):
    report = engine.coverage_gap([], [], radius_km=1.0, min_tier=Tier.HIGH)
    options = engine.siting_delta(report, [cool_space("anywhere", 52.5, -0.46)], radius_km=1.0)
    assert all(o.newly_covered == 0 for o in options)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/allocation -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'allocation'`

- [ ] **Step 3: Implement**

```python
# packages/allocation/src/allocation/distance.py
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance. A stateless transformation, so a function rather than
    a class. Real isochrones are a v0.2 concern — an 82-year-old's 800 metres is not
    a 40-year-old's."""
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))
```

```python
# packages/allocation/src/allocation/models.py
from dataclasses import dataclass

from contracts import Assessment


@dataclass(frozen=True, slots=True)
class Candidate:
    """A person considered for allocation, flattened to what the algorithms need."""

    person_id: str
    assessment: Assessment
    lives_alone: bool
    mobility_limited: bool
    lat: float
    lon: float
    has_cooling: bool


@dataclass(frozen=True, slots=True)
class Visit:
    person_id: str
    priority: float
    rationale: str


@dataclass(frozen=True, slots=True)
class AllocationPlan:
    visits: tuple[Visit, ...]
    unvisited: int
    capacity: int


@dataclass(frozen=True, slots=True)
class UncoveredPerson:
    person_id: str
    nearest_km: float | None  # None when no resource exists at all
    lat: float  # retained so siting_delta can measure against sites
    lon: float


@dataclass(frozen=True, slots=True)
class CoverageReport:
    uncovered: tuple[UncoveredPerson, ...]
    covered_count: int
    considered: int
    radius_km: float


@dataclass(frozen=True, slots=True)
class SitingOption:
    resource_id: str
    newly_covered: int
```

```python
# packages/allocation/src/allocation/plans.py
from collections.abc import Sequence

from allocation.distance import haversine_km
from allocation.models import (
    AllocationPlan,
    Candidate,
    CoverageReport,
    SitingOption,
    UncoveredPerson,
    Visit,
)
from contracts import Tier
from geography.loader import Resource


class AllocationEngine:
    """Turns risk tiers into deployment decisions.

    Pure over its arguments, so it replays against historical seasons: "what optimal
    deployment on 17 July 2025 would have looked like" is a runnable demo.

    The weights are constructor parameters, not module constants, because they are
    policy decisions a council may want to defend or change — not physics.
    """

    TIER_WEIGHT: dict[Tier, float] = {
        Tier.LOW: 0.0,
        Tier.ELEVATED: 1.0,
        Tier.HIGH: 3.0,
        Tier.SEVERE: 5.0,
    }

    def __init__(
        self,
        isolation_factor: float = 2.0,
        mobility_factor: float = 1.2,
        no_cooling_factor: float = 1.15,
    ) -> None:
        """isolation_factor defaults above the Severe/High tier ratio (5/3 = 1.67) so
        that living alone can outrank one full tier step. Below 1.67, tier dominates
        and the layer reverts to ranking on risk observed rather than harm averted.
        """
        self.isolation_factor = isolation_factor
        self.mobility_factor = mobility_factor
        self.no_cooling_factor = no_cooling_factor

    def priority_of(self, candidate: Candidate) -> float:
        """Harm averted per visit, not risk observed.

        A Severe-tier person with a live-in carer is already being watched; the
        marginal value of a council visit is lower than for a High-tier person alone.
        """
        score = self.TIER_WEIGHT[candidate.assessment.tier]
        if score == 0.0:
            return 0.0
        if candidate.lives_alone:
            score *= self.isolation_factor
        if candidate.mobility_limited:
            score *= self.mobility_factor
        if not candidate.has_cooling:
            score *= self.no_cooling_factor
        return score

    @staticmethod
    def rationale_for(candidate: Candidate) -> str:
        parts = [f"{candidate.assessment.tier.name.lower()} tier"]
        if candidate.lives_alone:
            parts.append("lives alone")
        if candidate.mobility_limited:
            parts.append("mobility limited")
        if not candidate.has_cooling:
            parts.append("no cooling at home")
        return ", ".join(parts)

    def rank_visits(self, candidates: Sequence[Candidate], capacity: int) -> AllocationPlan:
        """Order a cohort for a fixed number of welfare visits.

        Low tier is never scheduled: FR-18 already established it means no action
        beyond routine, and a visit spent there is a visit not spent elsewhere.
        """
        eligible = [(priority, c) for c in candidates if (priority := self.priority_of(c)) > 0.0]
        eligible.sort(key=lambda pair: (-pair[0], pair[1].person_id))
        chosen = eligible[:capacity]
        return AllocationPlan(
            visits=tuple(
                Visit(person_id=c.person_id, priority=round(p, 3), rationale=self.rationale_for(c))
                for p, c in chosen
            ),
            unvisited=len(eligible) - len(chosen),
            capacity=capacity,
        )

    @staticmethod
    def nearest_km(candidate: Candidate, resources: Sequence[Resource]) -> float | None:
        if not resources:
            return None
        return min(haversine_km(candidate.lat, candidate.lon, r.lat, r.lon) for r in resources)

    def coverage_gap(
        self,
        candidates: Sequence[Candidate],
        resources: Sequence[Resource],
        radius_km: float,
        min_tier: Tier,
    ) -> CoverageReport:
        """Who is at or above min_tier and beyond reach of any resource.

        Someone with cooling at home is covered by definition — the resource they
        need is the one they already have.
        """
        considered = [c for c in candidates if c.assessment.tier >= min_tier]
        uncovered: list[UncoveredPerson] = []
        covered = 0

        for c in considered:
            distance = None if c.has_cooling else self.nearest_km(c, resources)
            if c.has_cooling or (distance is not None and distance <= radius_km):
                covered += 1
            else:
                uncovered.append(
                    UncoveredPerson(
                        person_id=c.person_id, nearest_km=distance, lat=c.lat, lon=c.lon
                    )
                )

        return CoverageReport(
            uncovered=tuple(uncovered),
            covered_count=covered,
            considered=len(considered),
            radius_km=radius_km,
        )

    @staticmethod
    def siting_delta(
        report: CoverageReport, sites: Sequence[Resource], radius_km: float
    ) -> tuple[SitingOption, ...]:
        """Marginal coverage gained per candidate site, best first.

        Greedy and single-site: answers "which one site helps most", not "which set
        of three". Set cover is the right model for the latter and is a v0.2 concern.
        """
        options = [
            SitingOption(
                resource_id=site.id,
                newly_covered=sum(
                    1
                    for u in report.uncovered
                    if haversine_km(u.lat, u.lon, site.lat, site.lon) <= radius_km
                ),
            )
            for site in sites
        ]
        options.sort(key=lambda o: (-o.newly_covered, o.resource_id))
        return tuple(options)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/allocation -v`
Expected: PASS, 16 tests

- [ ] **Step 5: Commit**

```bash
git add packages/allocation tests/allocation
git commit -m "feat(allocation): AllocationEngine for visit ranking, coverage and siting"
```

---

## Task 13: Track stubs — actions and org views

**Files:**
- Create: `packages/actions/src/actions/checklist.py`, `notify.py`, `packages/org/src/org/models.py`, `views.py`
- Test: `tests/stubs/test_unclaimed_work.py`

**Interfaces:**
- Consumes: `contracts.Assessment`, `contracts.OrgType`
- Produces: `Org`, `Cohort`, `CohortMember` dataclasses; `ChecklistBuilder`, `NotificationPolicy`, `CouncilView`, `HospitalView`, `CareHomeView` — all stubs naming their track

- [ ] **Step 1: Write the failing test**

```python
# tests/stubs/test_unclaimed_work.py
"""Every stub must fail loudly and name its owning track. Red until claimed."""

import pytest
from actions.checklist import ChecklistBuilder
from actions.notify import NotificationPolicy
from contracts import OrgType
from org.models import CohortMember, Org
from org.views import CareHomeView, CouncilView, HospitalView
from predictors.cold_lag import ColdLagTracker
from predictors.heatwave import EnsembleHeatwave

STUBS = [
    (ChecklistBuilder().build, "Track A"),
    (NotificationPolicy().should_notify, "Track A"),
    (CouncilView().render, "Track B"),
    (HospitalView().render, "Track B"),
    (CareHomeView().render, "Track B"),
    (ColdLagTracker().track, "Track B"),
]


@pytest.mark.parametrize("fn,track", STUBS, ids=lambda v: getattr(v, "__qualname__", v))
def test_stub_raises_and_names_its_owner(fn, track):
    with pytest.raises(NotImplementedError, match=track):
        fn()


def test_ensemble_predictor_stub_names_track_b():
    with pytest.raises(NotImplementedError, match="Track B"):
        EnsembleHeatwave().forecast([30.0], horizon_days=1)


def test_three_tenant_types_are_implemented_and_icb_is_declared():
    assert {OrgType.COUNCIL, OrgType.HOSPITAL, OrgType.CARE_HOME} <= set(OrgType)
    assert OrgType.ICB in OrgType


def test_cohort_membership_requires_a_consent_basis():
    """SC-6 enforced structurally, not remembered."""
    with pytest.raises(TypeError):
        CohortMember(cohort_id="c", person_id="p")


def test_org_scopes_by_area_codes():
    org = Org(id="o", name="Bedford BC", type=OrgType.COUNCIL, area_codes=("E07000032",))
    assert org.area_codes == ("E07000032",)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stubs -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'actions'`

- [ ] **Step 3: Write the stubs and the tenancy models**

```python
# packages/actions/src/actions/checklist.py
class ChecklistBuilder:
    """Track A. FR-19: an ordered checklist derived solely from the reason codes.

    Read rows from core.corpus.Corpus.actions_for(). Never re-derive risk from raw
    exposure (AC-2), and never advise altering a prescription (SC-1).
    """

    def build(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track A owns this. See spec FR-19.")
```

```python
# packages/actions/src/actions/notify.py
class NotificationPolicy:
    """Track A. FR-21: dispatch on upward tier transition only.
    FR-22: at most one notification per person per six-hour period."""

    def should_notify(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track A owns this. See spec FR-21 and FR-22.")
```

```python
# packages/org/src/org/models.py
from dataclasses import dataclass

from contracts import OrgType


@dataclass(frozen=True, slots=True)
class Org:
    id: str
    name: str
    type: OrgType
    area_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Cohort:
    id: str
    org_id: str
    name: str


@dataclass(frozen=True, slots=True)
class CohortMember:
    cohort_id: str
    person_id: str
    consent_basis: str  # no default — SC-6 enforced by construction
```

```python
# packages/org/src/org/views.py
class CouncilView:
    """Track B. Tier distribution by ward, tomorrow's rank_visits, current
    coverage_gap. A pure query over the assessment table — no new persistence (AC-4).
    Answers: where do I send people tomorrow."""

    def render(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track B owns this. See spec section 8.")


class HospitalView:
    """Track B. Surge forecast: EpisodeForecast x cohort vulnerability distribution,
    with ensemble spread carried through as a confidence band. Answers: how many beds,
    and when.

    Demonstrator only — expert-judgement weighting projected forward, not an
    epidemiological model. Shows shape and timing, never a number to staff against.
    """

    def render(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track B owns this. See spec section 8.")


class CareHomeView:
    """Track B. Per-resident board sorted by tier. Answers: which of my forty
    residents tonight.

    Care homes already receive the UKHSA alerts, yet held 677 of the 1,504 heat
    deaths in 2025 — the gap there is resolution, not distribution.
    """

    def render(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track B owns this. See spec section 8.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stubs -v`
Expected: PASS — every stub raises with its track named, and `CohortMember` rejects a missing consent basis.

- [ ] **Step 5: Commit**

```bash
git add packages/actions packages/org tests/stubs
git commit -m "feat: typed stubs for actions and org views, each naming its track"
```

---

## Task 14: Remaining §13 verification gates

**Files:**
- Create: `tests/verification/conftest.py`, `test_no_cry_wolf.py`, `test_safety_corpus.py`

**Interfaces:**
- Consumes: `RiskScorer`, `VulnerabilityScorer`, `PersonaLoader`, `Corpus`
- Produces: `benign_season` fixture — 92 days of `ExposureFeatures`

- [ ] **Step 1: Write the failing test**

```python
# tests/verification/conftest.py
from datetime import date, timedelta

import pytest
from contracts import AlertLevel, ExposureFeatures, ExposureSource
from core.corpus import Corpus
from core.scoring import RiskScorer


@pytest.fixture(scope="session")
def corpus() -> Corpus:
    return Corpus.load()


@pytest.fixture(scope="session")
def scorer(corpus) -> RiskScorer:
    return RiskScorer(corpus)


@pytest.fixture(scope="session")
def benign_season() -> list[ExposureFeatures]:
    """92 days of unremarkable English summer. Nothing here should alarm anyone."""
    start = date(2025, 6, 1)
    return [
        ExposureFeatures(
            date=start + timedelta(days=i),
            overnight_min=12.0,
            peak_apparent=19.0,
            peak_air=19.0,
            hours_above_26=0,
            indoor_night_est=19.5,
            indoor_day_est=21.0,
            spell_day=0,
            alert_level=AlertLevel.NONE,
            source=ExposureSource.FIXTURE,
        )
        for i in range(92)
    ]
```

```python
# tests/verification/test_no_cry_wolf.py
"""Spec section 13. A low-vulnerability persona must return Low on all 92 days."""

import pytest
from contracts import Tier
from core.vulnerability import VulnerabilityScorer
from persons.loader import PersonaLoader


@pytest.fixture(scope="module")
def people():
    return PersonaLoader().load()


def test_low_vulnerability_persona_never_alarms_across_the_season(scorer, benign_season, people):
    v = VulnerabilityScorer().profile(people["margaret"])
    tiers = [scorer.assess(day, v).tier for day in benign_season]
    assert set(tiers) == {Tier.LOW}, (
        f"cried wolf on {sum(t is not Tier.LOW for t in tiers)} of 92 days"
    )


def test_even_the_frailest_persona_stays_low_in_benign_weather(scorer, benign_season, people):
    """FR-18 across a whole season, not just one day."""
    v = VulnerabilityScorer().profile(people["doris"])
    assert v.score == 10
    assert {scorer.assess(day, v).tier for day in benign_season} == {Tier.LOW}
```

```python
# tests/verification/test_safety_corpus.py
"""SC-1 merge gate. Zero matches required across the whole action corpus."""

import re

FORBIDDEN = re.compile(r"\b(stop|reduce|skip|halt|delay|alter|discontinue)\b", re.IGNORECASE)
MEDICATION_PREFIX = "med_"


def test_no_medication_action_advises_altering_a_prescription(corpus):
    offending = [
        (row.reason_code, row.text)
        for row in corpus.actions
        if row.reason_code.startswith(MEDICATION_PREFIX) and FORBIDDEN.search(row.text)
    ]
    assert not offending, f"SC-1 violation: {offending}"


def test_medication_actions_direct_to_a_professional(corpus):
    """SC-1: state the risk, then route to a pharmacist or GP."""
    med_rows = [r for r in corpus.actions if r.reason_code.startswith(MEDICATION_PREFIX)]
    assert med_rows, "the corpus has no medication rows to check"
    for row in med_rows:
        assert row.escalate_to in {"pharmacist", "gp"}, (
            f"{row.reason_code} states a medication risk without routing to a professional"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/verification -v`
Expected: FAIL — `fixture 'benign_season' not found` before `conftest.py` exists

- [ ] **Step 3: Fix whatever the gates catch**

These run against code that already exists, so failures here are **data** defects rather than missing implementations. If `test_medication_actions_direct_to_a_professional` fails, add `escalate_to` values to the offending rows in `data/seed/actions.csv`. If no-cry-wolf fails, the benign fixture is triggering a rule — check `indoor_day_est=21.0` against the cold thresholds in `EXPOSURE_RULES`.

- [ ] **Step 4: Run the full gate suite**

Run: `uv run pytest tests/verification -v`
Expected: PASS, all four gates green

- [ ] **Step 5: Commit**

```bash
git add tests/verification data/seed
git commit -m "test: no-cry-wolf and SC-1 safety corpus merge gates"
```

---

## Task 15: API read path

**Files:**
- Create: `services/api/pyproject.toml`, `services/api/src/api/main.py`
- Test: `tests/api/test_read_path.py`

**Interfaces:**
- Consumes: `RiskScorer`, `VulnerabilityScorer`, `PersonaLoader`, `Corpus`
- Produces: `GET /health`, `GET /people`, `GET /people/{person_id}/assessment`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_read_path.py
import pytest
from api.main import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_the_loaded_corpus_and_persona_counts(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["personas"] >= 3
    assert body["reason_codes"] == 23


def test_people_lists_every_seeded_persona(client):
    assert {p["id"] for p in client.get("/people").json()} >= {"doris", "harold", "margaret"}


def test_assessment_returns_tier_and_reasons_not_a_bare_score(client):
    """AC-2: reasons are the system of record for explanation."""
    body = client.get("/people/doris/assessment").json()
    assert body["tier"] in {"LOW", "ELEVATED", "HIGH", "SEVERE"}
    assert body["reasons"], "an assessment with no reasons is not explainable"
    assert all({"code", "title", "explanation"} <= set(r) for r in body["reasons"])


def test_indoor_estimates_are_labelled_modelled(client):
    """SC-5: modelled values labelled at every point of display."""
    exposure = client.get("/people/doris/assessment").json()["exposure"]
    assert "indoor_night_est_modelled" in exposure
    assert "indoor_day_est_modelled" in exposure


def test_response_states_it_is_not_medical_advice(client):
    """SC-2."""
    assert client.get("/people/doris/assessment").json()["not_medical_advice"] is True


def test_unknown_person_returns_404_not_500(client):
    assert client.get("/people/nobody/assessment").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api'`

- [ ] **Step 3: Implement the thin read path**

```python
# services/api/src/api/main.py
from datetime import date
from typing import Any

from contracts import AlertLevel, ExposureFeatures, ExposureSource, ReasonCode
from core.corpus import Corpus
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer
from fastapi import FastAPI, HTTPException
from persons.loader import PersonaLoader

app = FastAPI(title="Climatise Companion", version="0.1.0")

CORPUS = Corpus.load()
SCORER = RiskScorer(CORPUS)
VULNERABILITY = VulnerabilityScorer()
PERSONAS = PersonaLoader()

# Track 0 replaces this with a live Open-Meteo client behind the same type, so
# nothing downstream notices the swap. See spec section 11.
FIXTURE_EXPOSURE = ExposureFeatures(
    date=date(2025, 7, 19),
    overnight_min=17.0,
    peak_apparent=29.0,
    peak_air=29.0,
    hours_above_26=7,
    indoor_night_est=24.6,
    indoor_day_est=25.85,
    spell_day=3,
    alert_level=AlertLevel.NOT_CHECKED,
    source=ExposureSource.FIXTURE,
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "personas": len(PERSONAS.load()),
        "reason_codes": len(ReasonCode),
        "reasons_loaded": len(CORPUS.reasons),
    }


@app.get("/people")
def list_people() -> list[dict[str, Any]]:
    return [{"id": p.id, "name": p.name, "age_band": p.age_band} for p in PERSONAS.load().values()]


@app.get("/people/{person_id}/assessment")
def get_assessment(person_id: str) -> dict[str, Any]:
    person = PERSONAS.load().get(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"no person with id {person_id!r}")

    assessment = SCORER.assess(FIXTURE_EXPOSURE, VULNERABILITY.profile(person))
    return {
        "person_id": person.id,
        "tier": assessment.tier.name,
        "risk_score": assessment.risk_score,
        "exposure_score": assessment.exposure_score,
        "vulnerability_score": assessment.vulnerability_score,
        "reasons": [
            {"code": r.code, "title": r.title, "explanation": r.explanation, "weight": r.weight}
            for r in assessment.reasons
        ],
        "exposure": {
            # SC-5: the key name carries the label, so no caller can drop it.
            "indoor_night_est_modelled": FIXTURE_EXPOSURE.indoor_night_est,
            "indoor_day_est_modelled": FIXTURE_EXPOSURE.indoor_day_est,
            "overnight_min": FIXTURE_EXPOSURE.overnight_min,
            "peak_apparent": FIXTURE_EXPOSURE.peak_apparent,
            "source": FIXTURE_EXPOSURE.source,
        },
        "not_medical_advice": True,  # SC-2
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add services/api tests/api
git commit -m "feat(api): read path serving assessments with modelled labels"
```

---

## Task 16: Web surfaces and CONTRIBUTING

**Files:**
- Create: `web/shared/tier.js`, `web/companion/index.html`, `CONTRIBUTING.md`
- Move: prototypes into `web/national/index.html`, `web/explorer/index.html`, `docs/architecture.html`
- Test: `tests/web/test_tier_vocabulary.py`

**Interfaces:**
- Consumes: `GET /people/{id}/assessment`
- Produces: `TIERS` map and `renderTier(tier)` returning text + shape + colour

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_tier_vocabulary.py
"""NFR-07: tier must never be conveyed by colour alone."""

from pathlib import Path

import pytest
from contracts import Tier

WEB = Path(__file__).resolve().parents[2] / "web"
TIER_JS = WEB / "shared" / "tier.js"


@pytest.mark.parametrize("tier", list(Tier), ids=lambda t: t.name)
def test_every_tier_has_a_label_and_a_shape_not_just_a_colour(tier):
    assert tier.name in TIER_JS.read_text(), f"{tier.name} missing from the vocabulary"


def test_tier_vocabulary_defines_a_shape_channel():
    assert "shape" in TIER_JS.read_text(), "tier is colour-only — NFR-07 violation"


@pytest.mark.parametrize("surface", ["companion", "national", "explorer"])
def test_surfaces_import_the_shared_vocabulary(surface):
    html = (WEB / surface / "index.html").read_text()
    assert "shared/tier" in html, f"{surface} does not use the shared tier component"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web -v`
Expected: FAIL — `FileNotFoundError: web/shared/tier.js`

- [ ] **Step 3: Write the shared vocabulary and relocate the prototypes**

```javascript
// web/shared/tier.js
// NFR-07: every tier carries text, shape and colour. Never colour alone.
export const TIERS = {
  LOW:      { label: "Low",      shape: "circle",   colour: "#0B7B77", action: "No action beyond routine" },
  ELEVATED: { label: "Elevated", shape: "square",   colour: "#A85D18", action: "Check in today" },
  HIGH:     { label: "High",     shape: "triangle", colour: "#C05A2E", action: "Act before this evening" },
  SEVERE:   { label: "Severe",   shape: "diamond",  colour: "#B03A2C", action: "Act now — do not leave alone overnight" },
};

export function renderTier(tier) {
  const spec = TIERS[tier];
  if (!spec) throw new Error(`unknown tier: ${tier}`);
  const el = document.createElement("span");
  el.className = `tier tier-${tier.toLowerCase()} shape-${spec.shape}`;
  el.textContent = spec.label;
  el.setAttribute("role", "status");
  el.setAttribute("aria-label", `${spec.label} risk. ${spec.action}.`);
  return el;
}
```

```bash
mkdir -p web/national web/explorer docs
cp ~/Downloads/'climatise-national-view (1).html' web/national/index.html
cp ~/Downloads/climatise-geographic-explorer.html web/explorer/index.html
cp ~/Downloads/climate-companion-architecture.html docs/architecture.html
```

Add `<script type="module" src="../shared/tier.js"></script>` to each surface's `<head>`.

`web/companion/index.html` — caregiver PWA shell: 360 px layout, ≥16 px body text, ≥44 px tap targets, service worker caching the last assessment (NFR-04), escalation ladder rendering rung by rung so rung *n+1* is absent from the DOM until rung *n* is presented (§9.1).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/web -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Write CONTRIBUTING.md and commit**

`CONTRIBUTING.md` carries the track table with a "tests to green" column:

| Track | Owner | Directories | Tests to turn green |
|---|---|---|---|
| 0 — Core + data sources | person 1 | `contracts/` `core/` `exposure/` `persons/` `services/api/` | *(already green — keep it that way)* |
| A — Companion + voice | person 2 | `actions/` `checkin/` `services/voice/` `web/companion/` | `tests/stubs::ChecklistBuilder.build`, `::NotificationPolicy.should_notify` |
| B — Predictor + org | person 3 | `predictors/` `allocation/` `org/` `web/org/` `web/national/` `web/explorer/` | `tests/stubs::CouncilView.render`, `::HospitalView.render`, `::CareHomeView.render`, `::ColdLagTracker.track`, `test_ensemble_predictor_stub_names_track_b` |
| Data — profiles | anyone | `data/personas/*.yaml` | `tests/data/` stays green |
| Data — geography | anyone | `data/geography/*.yaml` | `tests/data/` stays green |

Plus the house rules: adding a persona or locality requires **no Python**; the four merge gates in `tests/verification/` must never go red; run `pre-commit run --files <changed>` before every push.

```bash
git add web docs CONTRIBUTING.md tests/web
git commit -m "feat(web): shared tier vocabulary, companion shell, prototypes relocated"
```

---

## Self-Review

**Spec coverage.** §2 layout → T1; §3 contracts → T2/T3; §4 core → T4/T5/T6; §5 predictors → T10; §6 voice → T11; §7 allocation → T12; §8 org → T13 (tenancy models green, views stubbed); §9 web → T16; §10 verification → T7/T14; §11 tracks and data surfaces → T8/T16; §12 deferred → stub docstrings throughout.

**Gap accepted:** `exposure/openmeteo.py` and `persons/geocode.py` appear in the file structure but have no task — the API serves `FIXTURE_EXPOSURE` instead. Deliberate, and it matches spec §11: the scaffold ships fixture-backed sources and Track 0 swaps in live clients behind the unchanged `ExposureFeatures` type as its first work. `ExposureSource` already distinguishes `FIXTURE` from `LIVE`, so nothing downstream is blocked or misled.

**Type consistency.** `RiskScorer(corpus).assess(exposure, vulnerability)` and `VulnerabilityScorer().profile(person)` are used identically in T6, T7, T8, T14 and T15. `Corpus.load()` returns an object exposing `.reasons`, `.actions`, `.med_classes`, `.actions_for()`, `.classify()` — consumed with those exact names in T4, T6, T11 and T14. `ActionRow` fields `.reason_code`, `.tier_min`, `.text`, `.escalate_to`, `.ordering` are consistent across T4, T11, T14. `Resource` is defined once in T8 and imported by T12. The `ReasonCode` count of 23 in T15's health test matches the 8 exposure + 15 vulnerability codes in T2.

**OOP conventions.** Every component is a class: `Corpus`, `VulnerabilityScorer`, `RiskScorer`, `IndoorModel`, `ExposureNormaliser`, `PersonaLoader`, `GeographyLoader`, `ThresholdHeatwave`, `CheckinScript`, `ConsoleVoice`, `AllocationEngine`, and the six stubs. `haversine_km` stays a function — a stateless transformation where a class would be ceremony. No leading underscores on any module-level name; helpers are `@staticmethod` on their owning class.
