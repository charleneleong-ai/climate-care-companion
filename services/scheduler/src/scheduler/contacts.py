"""Who to reach, and as which audience.

Separate from the persona because a persona describes a body in a building and
this describes a phone. The two change for different reasons: a dwelling offset
is stable for years, a caregiver's number changes when a daughter moves house.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from contracts import Audience

CONTACTS_PATH = Path(__file__).resolve().parents[4] / "data" / "seed" / "contacts.csv"


@dataclass(frozen=True, slots=True)
class Contact:
    person_id: str
    audience: Audience
    msisdn: str
    name: str


class ContactBook:
    """Lookup from (person, audience) to a reachable number.

    A missing caregiver is a real state, not a data error — someone can be
    registered with no one looking after them, and that is precisely the person
    the council view exists to find. Callers get `None` and carry on.
    """

    def __init__(self, contacts: tuple[Contact, ...]) -> None:
        self.by_key = {(c.person_id, c.audience): c for c in contacts}

    @classmethod
    def load(cls, path: Path | None = None) -> "ContactBook":
        with (path or CONTACTS_PATH).open(newline="") as fh:
            rows = csv.DictReader(row for row in fh if not row.startswith("#"))
            return cls(
                tuple(
                    Contact(
                        person_id=row["person_id"],
                        audience=Audience(row["audience"]),
                        msisdn=row["msisdn"],
                        name=row["name"],
                    )
                    for row in rows
                )
            )

    def get(self, person_id: str, audience: Audience) -> Contact | None:
        return self.by_key.get((person_id, audience))
