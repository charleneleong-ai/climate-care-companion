"""The Open-Meteo client, tested without touching the network."""

from datetime import UTC, date, datetime

import pytest
from contracts import ExposureSource
from exposure.openmeteo import FORECAST_DAYS, TIMEOUT_SECONDS, OpenMeteoClient

NOW = datetime(2025, 7, 19, 9, 0, tzinfo=UTC)
DAY = date(2025, 7, 19)


def hourly_day(base: float) -> list[float]:
    """24 values, coldest at 04:00 and hottest at 15:00 — the usual shape."""
    return [base + (6 if 11 <= h <= 18 else -2 if h <= 6 or h >= 22 else 0) for h in range(24)]


def body(days: int = FORECAST_DAYS, base: float = 20.0) -> dict:
    times, air, apparent = [], [], []
    for offset in range(days):
        stamp = date(2025, 7, 19 + offset).isoformat()
        times += [f"{stamp}T{h:02d}:00" for h in range(24)]
        air += hourly_day(base)
        apparent += hourly_day(base + 1)
    daily = [date(2025, 7, 19 + o).isoformat() for o in range(days)]
    return {
        "hourly": {
            "time": times,
            "temperature_2m": air,
            "apparent_temperature": apparent,
            "relative_humidity_2m": [55.0] * len(times),
        },
        "daily": {
            "time": daily,
            "temperature_2m_max": [base + 6] * days,
            "apparent_temperature_max": [base + 7] * days,
        },
    }


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeHttp:
    """Records calls so the request shape can be asserted, not assumed."""

    def __init__(self, payload: dict | None = None, fail: bool = False) -> None:
        self.payload = payload if payload is not None else body()
        self.fail = fail
        self.calls: list[dict] = []

    def get(self, url: str, params: dict, timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if self.fail:
            raise TimeoutError("Open-Meteo did not answer")
        return FakeResponse(self.payload)


def test_the_request_asks_for_hourly_data_over_at_least_72_hours():
    """FR-06. A current-conditions call cannot answer FR-07, which needs the
    22:00 to 07:00 window rather than a daily minimum."""
    http = FakeHttp()
    OpenMeteoClient(http).fetch(52.13, -0.46, NOW)
    params = http.calls[0]["params"]
    assert "temperature_2m" in params["hourly"]
    assert "apparent_temperature" in params["hourly"]
    assert params["forecast_days"] >= 3


def test_the_request_carries_the_nfr_03_timeout():
    http = FakeHttp()
    OpenMeteoClient(http).fetch(52.13, -0.46, NOW)
    assert http.calls[0]["timeout"] == TIMEOUT_SECONDS


def test_a_live_fetch_is_marked_live():
    forecast = OpenMeteoClient(FakeHttp()).fetch(52.13, -0.46, NOW)
    assert forecast.source is ExposureSource.LIVE


def test_a_timeout_falls_back_to_cache_and_says_so():
    """NFR-03 and NFR-04. A stale figure with its provenance attached is more
    use than a spinner."""
    client = OpenMeteoClient(FakeHttp())
    client.fetch(52.13, -0.46, NOW)

    client.http = FakeHttp(fail=True)
    fallback = client.fetch(52.13, -0.46, NOW)
    assert fallback.source is ExposureSource.CACHE
    assert fallback.daily_air_max == {"2025-07-19": 26.0, "2025-07-20": 26.0,
                                      "2025-07-21": 26.0}


def test_a_first_fetch_that_fails_has_nothing_to_fall_back_to():
    """Honest failure. Inventing a forecast would be worse than admitting there
    is none."""
    with pytest.raises(LookupError, match="nothing cached"):
        OpenMeteoClient(FakeHttp(fail=True)).fetch(52.13, -0.46, NOW)


def test_hourly_values_are_grouped_by_day():
    forecast = OpenMeteoClient(FakeHttp()).fetch(52.13, -0.46, NOW)
    assert set(forecast.hourly_air) == {"2025-07-19", "2025-07-20", "2025-07-21"}
    assert len(forecast.hourly_air["2025-07-19"]) == 24


def test_overnight_minimum_uses_the_night_window_not_the_daily_minimum():
    """The fixture dips to 18 overnight and 18 again at dawn, but sits at 20
    through the middle of the day. A daily minimum would be right by accident
    here; FR-07 must be right on purpose."""
    client = OpenMeteoClient(FakeHttp())
    forecast = client.fetch(52.13, -0.46, NOW)
    features = client.features_for(forecast, DAY, dwelling_offset=1.2)
    assert features.overnight_min == 18.0


def test_indoor_estimates_are_derived_from_the_dwelling_not_the_forecast():
    """Two homes under the same sky must not get the same bedroom."""
    client = OpenMeteoClient(FakeHttp())
    forecast = client.fetch(52.13, -0.46, NOW)
    flat = client.features_for(forecast, DAY, dwelling_offset=2.8)
    bungalow = client.features_for(forecast, DAY, dwelling_offset=0.5)
    assert flat.indoor_night_est > bungalow.indoor_night_est
    assert flat.indoor_night_est - bungalow.indoor_night_est == pytest.approx(2.3)


def test_spell_day_counts_only_days_up_to_the_one_being_scored():
    """A forecast knows about tomorrow. The spell counter must not, or every
    assessment inherits days that have not happened."""
    client = OpenMeteoClient(FakeHttp(body(base=25.0)))
    forecast = client.fetch(52.13, -0.46, NOW)
    first = client.features_for(forecast, date(2025, 7, 19), dwelling_offset=1.2)
    third = client.features_for(forecast, date(2025, 7, 21), dwelling_offset=1.2)
    assert first.spell_day == 1
    assert third.spell_day == 3


def test_provenance_survives_into_the_features():
    client = OpenMeteoClient(FakeHttp())
    client.fetch(52.13, -0.46, NOW)
    client.http = FakeHttp(fail=True)
    cached = client.fetch(52.13, -0.46, NOW)
    features = client.features_for(cached, DAY, dwelling_offset=1.2)
    assert features.source is ExposureSource.CACHE
