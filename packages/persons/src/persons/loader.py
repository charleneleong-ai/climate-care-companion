import csv
from pathlib import Path

import yaml
from contracts import AgeBand, Aspect, Condition, DwellingType, Med, MedClass, Person, Place
from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).resolve().parents[4] / "data"
PERSONAS_DIR = DATA_DIR / "personas"
OFFSETS_PATH = DATA_DIR / "seed" / "dwelling_offsets.csv"

FLOOR_BANDS = {0: "ground", 1: "middle"}
"""Anything above the first floor is treated as top. A third-floor flat and a
tenth-floor flat both sit under the roof's heat load as far as FR-11 is concerned."""


def floor_band(floor: int) -> str:
    return FLOOR_BANDS.get(floor, "top")


def load_dwelling_offsets(path: Path | None = None) -> dict[tuple[str, str, str], float]:
    """FR-11's dwelling_offset lookup, keyed on type, floor band and aspect.

    Without this the persona `place` block is validated and thrown away, and the
    indoor model has to be fed hardcoded numbers — which is how the API came to
    serve a fixture with the section 8.6 figures baked in.
    """
    with (path or OFFSETS_PATH).open(newline="") as fh:
        return {
            (row["dwelling_type"], row["floor"], row["aspect"]): float(row["offset"])
            for row in csv.DictReader(fh)
        }


class MedFile(BaseModel):
    drug_name: str
    drug_class: MedClass


class PlaceFile(BaseModel):
    postcode: str
    dwelling_type: DwellingType
    floor: int = 0
    aspect: Aspect = Aspect.SOUTH
    has_cooling: bool = False
    heating_affordable: bool = True

    def to_place(self, person_id: str, offsets: dict[tuple[str, str, str], float]) -> Place:
        key = (self.dwelling_type.value, floor_band(self.floor), self.aspect.value)
        if key not in offsets:
            raise ValueError(f"no dwelling offset for {key}")
        return Place(
            person_id=person_id,
            postcode=self.postcode,
            lat=0.0,
            lon=0.0,
            admin_district="",
            region="",
            dwelling_type=self.dwelling_type,
            floor=self.floor,
            aspect=self.aspect,
            has_cooling=self.has_cooling,
            heating_affordable=self.heating_affordable,
            dwelling_offset=offsets[key],
        )


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
        self.place_cache: dict[str, Place] | None = None

    def load(self) -> dict[str, Person]:
        if self.cache is None:
            self.read_all()
        return self.cache

    def places(self) -> dict[str, Place]:
        """Geocoding is Track 0's; lat, lon and district stay blank until the
        postcodes.io client lands. dwelling_offset is live now, which is the field
        the indoor model actually needs."""
        if self.place_cache is None:
            self.read_all()
        return self.place_cache

    def read_all(self) -> list[Person]:
        offsets = load_dwelling_offsets()
        people: dict[str, Person] = {}
        places: dict[str, Place] = {}
        for path in sorted(self.directory.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text())
            try:
                parsed = PersonaFile(**raw)
                people[parsed.id] = parsed.to_person()
                places[parsed.id] = parsed.place.to_place(parsed.id, offsets)
            except Exception as exc:
                raise ValueError(f"{path.name} is not a valid persona: {exc}") from exc
        self.cache, self.place_cache = people, places
        return list(people.values())
