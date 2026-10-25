"""V0_20 reuses the owned SYNTHETIC PG/TLS business runner; no real data."""

from backend.tests.safe_pilot import run as pilot


def main():
    pilot.TESTS = ["backend/tests/agronomic_history", "backend/tests/rolling_forecast"]
    original = pilot.command

    def command(arguments, environment, log, **kwargs):
        if arguments[:3] == ["npx", "playwright", "test"]:
            arguments = [
                *arguments[:3],
                "agronomic-v0-20.spec.ts",
                "spreadsheet-preview.spec.ts",
                "rolling-forecast.spec.ts",
                *arguments[3:],
            ]
        return original(arguments, environment, log, **kwargs)

    pilot.command = command
    pilot.main()


if __name__ == "__main__":
    main()
