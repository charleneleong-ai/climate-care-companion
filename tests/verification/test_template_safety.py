"""Merge gate for WhatsApp templates.

Meta approves templates for policy compliance, not clinical safety. These are
business-initiated messages sent to vulnerable people, so they carry the same
constraints as everything else the system says.
"""

import re

import pytest
from checkin.messages import TemplateLibrary
from checkin.sms import SmsFormatter
from core.corpus import FORBIDDEN_MEDICATION_ADVICE

VARIABLE = re.compile(r"\{\{(\d+)\}\}")


@pytest.fixture(scope="module")
def library() -> TemplateLibrary:
    return TemplateLibrary.load()


def test_no_template_advises_altering_a_prescription(library):
    """SC-1. A template is not a route around the medication constraint."""
    offending = [
        (key, template.body)
        for key, template in library.templates.items()
        if FORBIDDEN_MEDICATION_ADVICE.search(template.body)
    ]
    assert not offending, f"SC-1 violation in templates: {offending}"


def test_variable_placeholders_match_the_declared_variables(library):
    """A mismatch is rejected by Meta at send time, which on a heat night means the
    check-in silently fails to go out."""
    for key, template in library.templates.items():
        placeholders = {int(n) for n in VARIABLE.findall(template.body)}
        assert placeholders == set(range(1, len(template.variable_names) + 1)), (
            f"{key} declares {template.variable_names} but uses placeholders {placeholders}"
        )


def test_the_opener_asks_permission_rather_than_assessing(library):
    """Consent to be asked is not consent to be assessed. The opener requests a
    reply, which is also what opens the 24-hour window."""
    for key in ("checkin_opener", "checkin_opener_simple"):
        body = library.get(key).body.lower()
        assert "?" in body
        assert "reply" in body


def test_the_simplified_opener_is_single_clause(library):
    """Same comprehension property as the simplified questions."""
    for sentence in library.get("checkin_opener_simple").body.split("."):
        assert "," not in sentence, f"simplified opener has a subordinate clause: {sentence!r}"


def test_a_simplified_opener_exists_for_the_dementia_register(library):
    assert library.opener_for(simplified=True) != library.opener_for(simplified=False)


def test_the_no_answer_template_addresses_the_caregiver_not_the_person(library):
    """A missed check-in escalates outward. Messaging the person again would be
    retrying the thing that already failed."""
    template = library.get("caregiver_no_answer")
    assert "cared_for_name" in template.variable_names
    assert "did not get a reply" in template.body


def test_an_unapproved_template_name_raises_rather_than_sending_something_else(library):
    with pytest.raises(KeyError, match="approved in Meta Business Manager"):
        library.get("improvised_message")


def test_an_unbound_template_refuses_to_send(library):
    """Silently posting "Hello first_name" to an 88-year-old costs trust in the
    channel permanently, so it fails loudly instead."""
    unbound = library.get("checkin_opener")
    assert not unbound.is_bound
    with pytest.raises(ValueError, match="unbound variables"):
        SmsFormatter.render(unbound)


def test_binding_the_wrong_number_of_values_is_rejected(library):
    with pytest.raises(ValueError, match="declares 1 variables"):
        library.get("checkin_opener").bind("Doris", "extra")
