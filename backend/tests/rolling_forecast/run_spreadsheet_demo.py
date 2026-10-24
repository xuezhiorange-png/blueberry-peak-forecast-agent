"""Use the existing owned PostgreSQL runner for pre-data and S7/S8 browser regression."""

from backend.tests.safe_pilot import run as pilot


def main():
    pilot.TESTS = ["backend/tests/rolling_forecast"]
    original = pilot.command

    def command(arguments, environment, log, **kwargs):
        if arguments[:3] == ["npx", "playwright", "test"]:
            arguments = [
                *arguments[:3],
                "spreadsheet-preview.spec.ts",
                "rolling-forecast.spec.ts",
                *arguments[3:],
            ]
        return original(arguments, environment, log, **kwargs)

    pilot.command = command
    pilot.main()


if __name__ == "__main__":
    main()
