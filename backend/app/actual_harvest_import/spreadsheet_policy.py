from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpreadsheetParserPolicy:
    """Versioned transport limits for the Q2A-I3 spreadsheet boundary."""

    version: str = "q2a-i3-spreadsheet-policy-v1"
    header_policy: str = "STRICT_CANONICAL_V1"
    max_file_size_bytes: int = 10 * 1024 * 1024
    max_sheet_count: int = 1
    max_row_count: int = 100_000
    max_column_count: int = 32
    max_cell_text_length: int = 4_096
    max_uncompressed_xlsx_size_bytes: int = 50 * 1024 * 1024
    max_xlsx_compression_ratio: int = 100

    def __post_init__(self) -> None:
        if not self.version or not self.header_policy:
            raise ValueError("spreadsheet policy identity must be non-empty")
        for name in (
            "max_file_size_bytes",
            "max_sheet_count",
            "max_row_count",
            "max_column_count",
            "max_cell_text_length",
            "max_uncompressed_xlsx_size_bytes",
            "max_xlsx_compression_ratio",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")


DEFAULT_SPREADSHEET_POLICY = SpreadsheetParserPolicy()
