"""Loading .env.

Written after a live failure: credentials sat correctly in .env, nothing read the
file, and every send reported them absent. That is indistinguishable from a typo
in the token, so the seam gets its own tests.
"""

import os

import pytest
from checkin.env import load_env


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text('FIRST=one\nSECOND="two"\n# a comment\n')
    return path


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for key in ("FIRST", "SECOND"):
        monkeypatch.delenv(key, raising=False)


def test_values_reach_os_environ(env_file):
    load_env(env_file)
    assert os.environ["FIRST"] == "one"


def test_quotes_are_stripped(env_file):
    """A token read as '"abc"' authenticates against nothing and the error says
    only that the credentials were rejected."""
    load_env(env_file)
    assert os.environ["SECOND"] == "two"


def test_it_reports_what_it_loaded_and_not_the_values(env_file):
    assert sorted(load_env(env_file)) == ["FIRST", "SECOND"]


def test_a_real_environment_variable_wins(env_file, monkeypatch):
    """A deployment sets these properly. A stale .env in a checkout must not
    quietly beat it."""
    monkeypatch.setenv("FIRST", "from-the-environment")
    load_env(env_file)
    assert os.environ["FIRST"] == "from-the-environment"


def test_override_is_available_when_asked_for(env_file, monkeypatch):
    monkeypatch.setenv("FIRST", "from-the-environment")
    load_env(env_file, override=True)
    assert os.environ["FIRST"] == "one"


def test_a_missing_file_is_not_an_error(tmp_path):
    """Most deployments have no .env at all."""
    assert load_env(tmp_path / "absent") == []
