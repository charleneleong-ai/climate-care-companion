"""Open-Meteo client.

No API key and a generous free tier, which is why it beat the Met Office
DataHub for a hackathon build. Licensing and SLA risk are recorded in §12.2.

Deliberately richer than a current-conditions call. FR-06 asks for **hourly**
temperature, apparent temperature and humidity at least 72 hours ahead, and
FR-07 defines the overnight minimum as the minimum between 22:00 and 07:00. A
daily minimum cannot answer that: it includes the afternoon, and an unusually
cold dawn is not the same signal as a night that never cooled.

NFR-03 and NFR-04 live here too. A three-second timeout, then the last good
snapshot. The specification asks for a cache rather than a recomputation, which
is why the front end does not need its own scoring engine.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any

from contracts import AlertLevel, ExposureFeatures, ExposureSource
from exposure.indoor import IndoorModel
from exposure.normalise import ExposureNormaliser

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

TIMEOUT_SECONDS = 3.0
"""NFR-03. Past this the cache is better than a spinner — a caregiver checking
on someone at nine at night will not wait, and a stale figure with its
provenance attached is more use than nothing."""

HOURLY_FIELDS = ("temperature_2m", "apparent_temperature", "relative_humidity_2m")
DAILY_FIELDS = ("temperature_2m_max", "apparent_temperature_max")
FORECAST_DAYS = 3
"""FR-06 asks for at least 72 hours."""

EPISODE_THRESHOLD = 24.0
"""Matches predictors.heatwave. Used only for the spell-day count here."""


@dataclass(frozen=True, slots=True)
class Forecast:
    """One place, several days. The raw shape before scoring sees it."""

    latitude: float
    longitude: float
    hourly_air: dict[str, list[float]]
    """Keyed by ISO date, 24 values each."""
    hourly_apparent: dict[str, list[float]]
    daily_air_max: dict[str, float]
    daily_apparent_max: dict[str, float]
    retrieved_at: datetime
    source: ExposureSource


class OpenMeteoClient:
    """Fetches forecasts and turns them into ExposureFeatures.

    The client is injected rather than constructed so tests never touch the
    network, and so a caller can supply one with its own retry policy.
    """

    def __init__(
        self,
        http: Any = None,
        indoor: IndoorModel | None = None,
        normaliser: ExposureNormaliser | None = None,
    ) -> None:
        self.http = http
        self.indoor = indoor or IndoorModel()
        self.normaliser = normaliser or ExposureNormaliser()
        self.cache: dict[tuple[float, float], Forecast] = {}

    @staticmethod
    def params(latitude: float, longitude: float) -> dict[str, Any]:
        return {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(HOURLY_FIELDS),
            "daily": ",".join(DAILY_FIELDS),
            "timezone": "Europe/London",
            "forecast_days": FORECAST_DAYS,
        }

    @staticmethod
    def group_hourly(times: list[str], values: list[float]) -> dict[str, list[float]]:
        """Open-Meteo returns one flat array; scoring wants it per day."""
        grouped: dict[str, list[float]] = {}
        for stamp, value in zip(times, values, strict=True):
            grouped.setdefault(stamp[:10], []).append(value)
        return grouped

    def parse(
        self, body: dict[str, Any], latitude: float, longitude: float, now: datetime
    ) -> Forecast:
        hourly, daily = body["hourly"], body["daily"]
        return Forecast(
            latitude=latitude,
            longitude=longitude,
            hourly_air=self.group_hourly(hourly["time"], hourly["temperature_2m"]),
            hourly_apparent=self.group_hourly(hourly["time"], hourly["apparent_temperature"]),
            daily_air_max=dict(zip(daily["time"], daily["temperature_2m_max"], strict=True)),
            daily_apparent_max=dict(
                zip(daily["time"], daily["apparent_temperature_max"], strict=True)
            ),
            retrieved_at=now,
            source=ExposureSource.LIVE,
        )

    def fetch(self, latitude: float, longitude: float, now: datetime) -> Forecast:
        """Live if it answers in time, otherwise the last good snapshot.

        A failure is not an error here. NFR-04 requires the system to work with
        no network at all, and the caller can tell the difference because
        `source` says CACHE rather than LIVE.
        """
        key = (round(latitude, 4), round(longitude, 4))
        if self.http is None:
            return self.cached_or_raise(key)
        try:
            response = self.http.get(
                FORECAST_URL,
                params=self.params(latitude, longitude),
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            forecast = self.parse(response.json(), latitude, longitude, now)
        except Exception:
            return self.cached_or_raise(key)
        self.cache[key] = forecast
        return forecast

    def cached_or_raise(self, key: tuple[float, float]) -> Forecast:
        cached = self.cache.get(key)
        if cached is None:
            raise LookupError(
                f"no forecast for {key} and nothing cached — the first fetch for a "
                f"place cannot fall back"
            )
        return replace(cached, source=ExposureSource.CACHE)

    def features_for(
        self,
        forecast: Forecast,
        day: date,
        dwelling_offset: float,
        alert_level: AlertLevel = AlertLevel.NOT_CHECKED,
    ) -> ExposureFeatures:
        """FR-07 to FR-11 applied to one day of a forecast."""
        key = day.isoformat()
        hours = {index: value for index, value in enumerate(forecast.hourly_air[key])}
        overnight_min = self.normaliser.overnight_minimum(hours)
        peak_air = forecast.daily_air_max[key]
        peak_apparent = forecast.daily_apparent_max[key]

        ordered = sorted(forecast.daily_apparent_max)
        peaks_to_date = [forecast.daily_apparent_max[d] for d in ordered if d <= key]

        return ExposureFeatures(
            date=day,
            overnight_min=overnight_min,
            peak_apparent=peak_apparent,
            peak_air=peak_air,
            hours_above_26=self.normaliser.hours_above(hours, 26.0),
            indoor_night_est=self.indoor.night(overnight_min, peak_air, dwelling_offset),
            indoor_day_est=self.indoor.day(overnight_min, peak_air, dwelling_offset),
            spell_day=self.normaliser.spell_day(peaks_to_date, EPISODE_THRESHOLD),
            alert_level=alert_level,
            source=forecast.source,
        )
