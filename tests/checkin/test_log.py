"""The check-in log.

Its job is to make a missed call visible tomorrow morning. The tests are mostly
about what survives — a restart, a corrupt file, a half-written one — because a
record that vanishes is indistinguishable from a check-in that went fine.
"""

import pytest
from checkin.log import Channel, CheckinLog, CheckinRecord, Outcome, now_iso


@pytest.fixture
def log(tmp_path) -> CheckinLog:
    return CheckinLog(tmp_path / "checkins.json")


def entry(outcome: Outcome, person_id: str = "doris") -> CheckinRecord:
    return CheckinRecord(
        person_id=person_id,
        channel=Channel.VOICE,
        outcome=outcome,
        started_at=now_iso(),
    )


class TestPersistence:
    def test_a_record_survives_a_restart(self, log, tmp_path):
        log.record(entry(Outcome.COMPLETED))
        assert CheckinLog(tmp_path / "checkins.json").for_person("doris")

    @pytest.mark.parametrize(
        "contents",
        ["{ not json", '[{"person_id": "doris"}]', '{"not": "a list"}'],
        ids=["truncated", "missing-keys", "wrong-shape"],
    )
    def test_a_damaged_file_loads_empty_rather_than_raising(self, tmp_path, contents):
        """The voice service holds one of these at module level, so raising here
        would stop every check-in rather than losing one."""
        path = tmp_path / "checkins.json"
        path.write_text(contents)
        store = CheckinLog(path)
        assert store.records == []
        assert store.unreadable is not None

    def test_writes_leave_no_temporary_behind(self, log, tmp_path):
        log.record(entry(Outcome.NO_ANSWER))
        assert not list(tmp_path.glob("*.tmp"))


class TestConsecutiveMissed:
    """What the escalation policy reads to tell a pattern from an incident."""

    def test_a_clean_history_counts_none(self, log):
        log.record(entry(Outcome.COMPLETED))
        assert log.consecutive_missed("doris") == 0

    def test_it_counts_the_current_run_only(self, log):
        """Three missed in March, answered since, is not the person this is for."""
        for outcome in (Outcome.NO_ANSWER, Outcome.NO_ANSWER, Outcome.COMPLETED):
            log.record(entry(outcome))
        assert log.consecutive_missed("doris") == 0

    def test_a_run_of_silence_is_counted(self, log):
        log.record(entry(Outcome.COMPLETED))
        log.record(entry(Outcome.NO_ANSWER))
        log.record(entry(Outcome.NO_ANSWER))
        assert log.consecutive_missed("doris") == 2

    def test_an_abandoned_call_counts_as_missed(self, log):
        """Hanging up half way through leaves the same question unanswered."""
        log.record(entry(Outcome.ABANDONED))
        assert log.consecutive_missed("doris") == 1

    def test_one_person_run_does_not_affect_another(self, log):
        log.record(entry(Outcome.NO_ANSWER, person_id="doris"))
        log.record(entry(Outcome.NO_ANSWER, person_id="harold"))
        log.record(entry(Outcome.COMPLETED, person_id="doris"))
        assert log.consecutive_missed("doris") == 0
        assert log.consecutive_missed("harold") == 1
