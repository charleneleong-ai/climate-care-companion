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
    """Discovers and validates persona files.

    A contribution surface: adding a persona is a new YAML file and no Python edit,
    so persona authors never serialise behind a code track.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or PERSONAS_DIR
        self.cache: dict[str, Person] | None = None

    def load(self) -> dict[str, Person]:
        if self.cache is None:
            self.cache = {person.id: person for person in self.read_all()}
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
