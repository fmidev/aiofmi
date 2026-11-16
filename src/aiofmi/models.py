"""Data models returned by aiofmi."""

from dataclasses import dataclass
from datetime import date, datetime

# FMI adds this to a SmartSymbol code when the sun is below the horizon.
_NIGHT_OFFSET = 100


@dataclass(frozen=True, slots=True, kw_only=True)
class Location:
    """The place FMI resolved a forecast request to."""

    name: str | None
    """Name of the nearest known place. Not a stable identifier."""
    region: str | None
    country: str | None
    timezone: str | None
    """IANA time zone name, such as ``Europe/Helsinki``."""
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True, kw_only=True)
class ForecastPoint:
    """Forecast values for one moment. A value FMI does not provide is None."""

    time: datetime
    """Time the values are valid for, timezone-aware, in UTC."""
    temperature: float | None
    """Air temperature, °C."""
    feels_like: float | None
    """Apparent temperature, °C."""
    dew_point: float | None
    """Dew point temperature, °C."""
    humidity: float | None
    """Relative humidity, %."""
    pressure: float | None
    """Air pressure at sea level, hPa."""
    wind_speed: float | None
    """Wind speed, m/s."""
    wind_direction: float | None
    """Direction the wind blows from, degrees."""
    wind_gust: float | None
    """Highest gust during the preceding hour, m/s."""
    cloud_cover: float | None
    """Total cloud cover, %."""
    precipitation: float | None
    """Precipitation accumulated during the preceding hour, mm."""
    precipitation_probability: float | None
    """Probability of precipitation, %."""
    thunder_probability: float | None
    """Probability of thunder, %."""
    smart_symbol: int | None
    """FMI SmartSymbol weather code as sent, with 100 added at night."""

    @property
    def symbol(self) -> int | None:
        """SmartSymbol code without the night offset."""
        if self.smart_symbol is None:
            return None
        return self.smart_symbol % _NIGHT_OFFSET

    @property
    def is_daytime(self) -> bool | None:
        """Whether the sun is up, as encoded in the SmartSymbol code."""
        if self.smart_symbol is None:
            return None
        return self.smart_symbol < _NIGHT_OFFSET


@dataclass(frozen=True, slots=True, kw_only=True)
class PointForecast:
    """A point forecast as a time series."""

    location: Location
    issued: datetime | None
    """Analysis time of the forecast, timezone-aware, in UTC."""
    points: tuple[ForecastPoint, ...]
    """Forecast points in chronological order."""


@dataclass(frozen=True, slots=True, kw_only=True)
class DailyForecast:
    """Forecast values aggregated over one local calendar day."""

    date: date
    points: tuple[ForecastPoint, ...]
    """The points of the day. Precipitation also counts the next midnight's point
    instead of the day's first, as each value covers the preceding hour."""
    temperature_max: float | None
    """Highest temperature, °C."""
    temperature_min: float | None
    """Lowest temperature, °C."""
    precipitation: float | None
    """Total precipitation, mm."""
    precipitation_probability: float | None
    """Highest probability of precipitation, %."""
    wind_speed: float | None
    """Highest wind speed, m/s."""
    wind_direction: float | None
    """Wind direction at the time of the highest wind speed, degrees."""
    wind_gust: float | None
    """Highest gust, m/s."""
    smart_symbol: int | None
    """SmartSymbol code at 15:00 local time, as on FMI's own services.

    On the first day, the code closest to 15:00, which after 15:00 can be a
    night-time code.
    """

    @property
    def symbol(self) -> int | None:
        """SmartSymbol code without the night offset."""
        if self.smart_symbol is None:
            return None
        return self.smart_symbol % _NIGHT_OFFSET
