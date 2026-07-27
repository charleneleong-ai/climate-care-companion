"""Vercel's entrypoint for the Python core.

Vercel loads a top-level `app` from one of a handful of filenames, this being
one of them. The work here is making a uv workspace importable under a plain
`pip install -r requirements.txt`, which is what the Python preset runs.

pip cannot install the thirteen workspace members: they resolve to each other
through `{ workspace = true }`, which is a uv concept with no pip equivalent.
But it does not need to. Vercel bundles every file in the project, so the
packages are already present at their normal paths — they only need to be
importable, and adding each `src` to `sys.path` does that without an install
step, a build command, or a second copy of anything.

Layout is load-bearing and must not be flattened: `persons.loader` locates the
persona corpus as `Path(__file__).parents[4] / "data"`, which is correct only
while the tree keeps its shape. That is also why `vercel.json` excludes tests
and the web app but never `data/`.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

for source in (*sorted(ROOT.glob("packages/*/src")), *sorted(ROOT.glob("services/*/src"))):
    if (entry := str(source)) not in sys.path:
        sys.path.insert(0, entry)

from api.main import app  # noqa: E402  — the path above has to be set up first

__all__ = ["app"]
