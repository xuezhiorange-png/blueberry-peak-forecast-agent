"""Literal fictional labels; imported ONLY by independent synthetic Phase B."""


def fixture_payload() -> dict[str, list[str]]:
    return {
        "SYNTHETIC-BASE-A": [
            str(v)
            for v in (8, 8, 8, 8, 11, 13, 14, 20, 25, 30, 35, 40, 35, 25, 7, 6, 5, 4, 3, 4, 6)
        ],
        "SYNTHETIC-BASE-B": ["20"] * 7 + ["60"] * 7 + ["10"] * 7,
        "SYNTHETIC-BASE-C": ["0"] * 21,
        "SYNTHETIC-BASE-D": ["10"] * 21,
    }
