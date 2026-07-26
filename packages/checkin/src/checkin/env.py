"""Load `.env` from the repo root.

Every channel in this package reads its credentials from `os.environ`, which is
correct — but nothing was putting them there, so a `.env` file written by hand sat
inert and `TwilioChannel()` raised "credentials are absent" while the credentials
were plainly on disk. That failure is indistinguishable from a typo in the token,
which is a bad half-hour to hand anyone.

Called explicitly by the entrypoints rather than on package import: importing a
module should not reach out to the filesystem, and a test that sets its own
environment must not have it silently overwritten by whatever is in the repo.
"""

import os
from pathlib import Path

from dotenv import dotenv_values

ENV_PATH = Path(__file__).resolve().parents[4] / ".env"


def load_env(path: Path | None = None, override: bool = False) -> list[str]:
    """Returns the names loaded, never the values.

    A real environment variable wins over the file by default — a deployment sets
    these properly, and a stale `.env` left in a checkout must not quietly beat it.
    """
    target = path or ENV_PATH
    if not target.exists():
        return []

    loaded: list[str] = []
    for key, value in dotenv_values(target).items():
        if value is None:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded
