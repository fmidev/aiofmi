"""Exceptions raised by aiofmi."""


class FmiError(Exception):
    """Base class for all aiofmi errors."""


class FmiConnectionError(FmiError):
    """The service could not be reached."""


class FmiTimeoutError(FmiConnectionError):
    """The service did not answer in time."""


class FmiResponseError(FmiError):
    """The service answered with something that could not be used."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        """Store the HTTP status alongside the message."""
        super().__init__(message)
        self.status = status


class FmiRateLimitError(FmiError):
    """The service refused the request because of its rate limits."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        """Store the number of seconds the service asked the caller to wait."""
        super().__init__(message)
        self.retry_after = retry_after


class FmiRequestError(FmiError):
    """The service rejected the request; repeating it unchanged will not help."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        """Store the OWS exception code alongside the message."""
        super().__init__(message)
        self.code = code


class FmiNoDataError(FmiRequestError):
    """The service has no data for the requested location."""
