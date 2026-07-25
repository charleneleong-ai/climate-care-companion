from collections.abc import Sequence


class ExposureNormaliser:
    """Turns an hourly forecast into the features that predict harm (FR-07 to FR-09),
    rather than the ones the forecast happens to hand you."""

    NIGHT_HOURS: tuple[int, ...] = (22, 23, 0, 1, 2, 3, 4, 5, 6, 7)

    @classmethod
    def overnight_minimum(cls, hourly_temps: dict[int, float]) -> float:
        """FR-07. Minimum air temperature between 22:00 and 07:00.

        A daytime low is irrelevant to overnight recovery, so the window is not
        simply the minimum of the day.
        """
        window = [hourly_temps[h] for h in cls.NIGHT_HOURS if h in hourly_temps]
        if not window:
            raise ValueError("no hourly temperatures in the 22:00-07:00 window")
        return min(window)

    @staticmethod
    def spell_day(daily_peaks: Sequence[float], threshold: float) -> int:
        """FR-09. Consecutive days meeting the episode threshold, counting back
        from the most recent day. A break in the spell resets the count."""
        count = 0
        for peak in reversed(daily_peaks):
            if peak < threshold:
                break
            count += 1
        return count

    @staticmethod
    def hours_above(hourly_temps: dict[int, float], threshold: float) -> int:
        return sum(1 for temp in hourly_temps.values() if temp >= threshold)
