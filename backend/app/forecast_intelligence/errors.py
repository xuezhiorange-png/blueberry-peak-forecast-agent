"""Stable, value-free error boundary for hierarchy reconciliation."""


class HierarchicalForecastError(ValueError):
    def __init__(self, code: str, status_code: int = 422):
        self.code = code
        self.status_code = status_code
        super().__init__(code)
