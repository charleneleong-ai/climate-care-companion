from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

GEOGRAPHY_DIR = Path(__file__).resolve().parents[4] / "data" / "geography"


@dataclass(frozen=True, slots=True)
class Resource:
    id: str
    type: str
    """cool_space | pharmacy | warm_bank | council_welfare"""
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
    """Discovers and validates locality files.

    A contribution surface: adding a locality is a new YAML file and no Python edit.
    Geographic breadth is what makes coverage_gap and siting_delta produce a demo
    worth watching rather than a function with two rows of input.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or GEOGRAPHY_DIR
        self.cache: dict[str, Locality] | None = None

    def load(self) -> dict[str, Locality]:
        if self.cache is None:
            self.cache = {locality.name: locality for locality in self.read_all()}
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

    def resources_of_type(self, resource_type: str) -> tuple[Resource, ...]:
        return tuple(
            resource
            for locality in self.load().values()
            for resource in locality.resources
            if resource.type == resource_type
        )
