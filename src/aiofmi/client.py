"""Client for FMI's open data WFS service."""

import asyncio
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

from aiohttp import ClientError, ClientSession

from ._wfs import FORECAST_PARAMETERS, parse_exception_report, parse_forecast
from .exceptions import (
    FmiConnectionError,
    FmiRateLimitError,
    FmiResponseError,
    FmiTimeoutError,
)
from .models import Forecast

WFS_URL = "https://opendata.fmi.fi/wfs"

_FORECAST_QUERY = (
    "fmi::forecast::edited::weather::scandinavia::point::multipointcoverage"
)
_MAX_LATITUDE = 90
_MAX_LONGITUDE = 180


def _format_time(value: datetime) -> str:
    if value.tzinfo is None:
        msg = "Times must be timezone-aware"
        raise ValueError(msg)
    # A "+00:00" suffix would reach the service as a space.
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _retry_after(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class FmiClient:
    """Client for FMI's open data."""

    def __init__(
        self,
        session: ClientSession,
        *,
        request_timeout: float = 30,
        url: str = WFS_URL,
    ) -> None:
        """Use ``session`` for all requests. The session is never closed here."""
        self._session = session
        self._request_timeout = request_timeout
        self._url = url

    async def forecast(
        self,
        latitude: float,
        longitude: float,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        timestep: timedelta = timedelta(hours=1),
    ) -> Forecast:
        """Fetch FMI's official forecast for a point in Finland or nearby.

        The series runs from ``start`` (default: the beginning of the current
        hour) to ``end`` (default: ten days after ``start``) or to the end of
        the forecast, whichever comes first.
        """
        if not (
            -_MAX_LATITUDE <= latitude <= _MAX_LATITUDE
            and -_MAX_LONGITUDE <= longitude <= _MAX_LONGITUDE
        ):
            msg = f"Invalid coordinates: {latitude}, {longitude}"
            raise ValueError(msg)
        if start is None:
            start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        if end is None:
            end = start + timedelta(days=10)
        if end <= start:
            msg = "The end time must be after the start time"
            raise ValueError(msg)
        minutes, remainder = divmod(timestep.total_seconds(), 60)
        if minutes < 1 or remainder:
            msg = "The timestep must be a positive number of whole minutes"
            raise ValueError(msg)
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "getFeature",
            "storedquery_id": _FORECAST_QUERY,
            "latlon": f"{latitude},{longitude}",
            "starttime": _format_time(start),
            "endtime": _format_time(end),
            "timestep": str(int(minutes)),
            "parameters": ",".join(FORECAST_PARAMETERS.values()),
        }
        return parse_forecast(await self._get(params))

    async def _get(self, params: dict[str, str]) -> bytes:
        try:
            async with (
                asyncio.timeout(self._request_timeout),
                self._session.get(self._url, params=params) as response,
            ):
                status = response.status
                retry_after = response.headers.get("Retry-After")
                body = await response.read()
        except TimeoutError as err:
            msg = "Timeout while connecting to FMI"
            raise FmiTimeoutError(msg) from err
        except ClientError as err:
            msg = f"Error while connecting to FMI: {err}"
            raise FmiConnectionError(msg) from err

        if status == HTTPStatus.OK:
            return body
        if status == HTTPStatus.BAD_REQUEST:
            raise parse_exception_report(body)
        if status == HTTPStatus.TOO_MANY_REQUESTS:
            msg = "FMI's request rate limit was exceeded"
            raise FmiRateLimitError(msg, retry_after=_retry_after(retry_after))
        msg = f"FMI returned HTTP status {status}"
        raise FmiResponseError(msg, status=status)
