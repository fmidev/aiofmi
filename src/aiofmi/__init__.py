"""Async client for the Finnish Meteorological Institute's open data."""

from .client import FmiClient
from .daily import daily_forecasts
from .exceptions import (
    FmiConnectionError,
    FmiError,
    FmiNoDataError,
    FmiRateLimitError,
    FmiRequestError,
    FmiResponseError,
    FmiTimeoutError,
)
from .models import DailyForecast, ForecastPoint, Location, PointForecast

__all__ = [
    "DailyForecast",
    "FmiClient",
    "FmiConnectionError",
    "FmiError",
    "FmiNoDataError",
    "FmiRateLimitError",
    "FmiRequestError",
    "FmiResponseError",
    "FmiTimeoutError",
    "ForecastPoint",
    "Location",
    "PointForecast",
    "daily_forecasts",
]
