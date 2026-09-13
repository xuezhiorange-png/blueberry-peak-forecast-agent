"""Transport-independent, non-sensitive product failure vocabulary."""


class AreaForecastRequestError(ValueError):
    code = "AREA_FORECAST_UNSUPPORTED_FARM_HISTORY"
    status_code = 422

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AreaForecastInputError(AreaForecastRequestError):
    code = "AREA_FORECAST_REQUEST_INVALID"


class AreaForecastAuthorityError(ValueError):
    code = "AREA_FORECAST_AUTHORITY_UNAVAILABLE"
    status_code = 503

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
