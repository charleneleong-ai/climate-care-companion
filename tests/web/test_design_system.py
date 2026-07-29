"""The CoolBuddy typefaces have to survive the whole chain to reach a screen.

Four links, and a break in any one of them falls back to system fonts. That
failure is quiet: the page renders, the layout holds, everything is legible, and
the only symptom is that advice written to sound like a person now looks like
output. Nobody files a bug for that.

    layout.tsx        imports the faces and names their CSS variables
    layout.tsx        puts those variables on <html>
    tailwind.config   maps `sans` and `prose` at those variables
    globals.css       `.prose-voice` asks for the prose family

What this cannot check is what a browser did with it — see the last test. It was
confirmed by hand once, on 29 July 2026, by reading `getComputedStyle` on a
running page: Signika and Newsreader both loaded and applied, no fallback.

Worth knowing that `next/font` fails the *build* if it cannot fetch a face, so
"the download silently failed" is not among the things that can go wrong here.
The wiring is.
"""

from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web" / "app"
LAYOUT = WEB / "src" / "app" / "layout.tsx"
TAILWIND = WEB / "tailwind.config.ts"
GLOBALS = WEB / "src" / "app" / "globals.css"

UI_VAR = "--font-ui"
PROSE_VAR = "--font-prose"


@pytest.fixture(scope="module")
def layout() -> str:
    return LAYOUT.read_text()


@pytest.fixture(scope="module")
def tailwind() -> str:
    return TAILWIND.read_text()


@pytest.fixture(scope="module")
def styles() -> str:
    return GLOBALS.read_text()


@pytest.mark.parametrize("face", ["Signika", "Newsreader"])
def test_both_faces_are_self_hosted_through_next_font(layout, face):
    """`next/font`, not a stylesheet link. A CDN would put a render-blocking
    third party in front of advice someone opened because they were worried,
    and would fail on the offline path NFR-04 requires."""
    assert f"{face}(" in layout
    assert "next/font/google" in layout


@pytest.mark.parametrize("variable", [UI_VAR, PROSE_VAR])
def test_each_face_names_the_variable_the_rest_of_the_chain_reads(layout, variable):
    assert f"'{variable}'" in layout


def test_the_variables_reach_the_document(layout):
    """Declared and then never applied is the easiest link to drop, because
    everything still compiles and the page still renders."""
    html = layout[layout.index("<html") : layout.index(">", layout.index("<html"))]
    assert "signika.variable" in html
    assert "newsreader.variable" in html


@pytest.mark.parametrize(("family", "variable"), [("sans", UI_VAR), ("prose", PROSE_VAR)])
def test_tailwind_maps_each_family_at_its_variable(tailwind, family, variable):
    line = next(ln for ln in tailwind.splitlines() if ln.strip().startswith(f"{family}:"))
    assert f"var({variable})" in line


@pytest.mark.parametrize("family", ["sans", "prose"])
def test_each_family_keeps_a_fallback_stack(tailwind, family):
    """If a face ever does fail, the next name along should be a system font
    rather than the browser's default serif."""
    line = next(ln for ln in tailwind.splitlines() if ln.strip().startswith(f"{family}:"))
    assert line.count(",") >= 2, f"{family} has no fallback after the webfont"


def test_the_prose_class_asks_for_the_prose_family(styles):
    """`.prose-voice` is what puts the serif on reasons and advice. Without it
    the face loads, costs bytes, and is never seen."""
    block = styles[styles.index(".prose-voice") : styles.index("}", styles.index(".prose-voice"))]
    assert "fontFamily.prose" in block


def test_the_prose_class_is_actually_used():
    """A design token nothing references is a token that has already drifted."""
    used = [path for path in (WEB / "src").rglob("*.tsx") if "prose-voice" in path.read_text()]
    assert used, "nothing applies .prose-voice, so every sentence is in the UI face"


def test_this_file_cannot_prove_a_browser_rendered_them():
    """Deliberate placeholder, so the gap is visible in the suite.

    These are string checks. They would pass if the font files 404'd at run
    time, or if a later rule overrode the family. Closing this properly needs a
    browser in CI; until there is one, the runtime check is a manual step
    recorded in this module's docstring.
    """
    assert LAYOUT.exists()
