"""Thin S7 selection of the existing S5 owned-PostgreSQL/SIGTERM runner.

python -m backend.tests.rolling_forecast.run --output /tmp/SYNTHETIC-s7-unique --browser
No alternate resource lifecycle, global process cleanup or real-source access.
"""

from backend.tests.safe_pilot import run as pilot


def main():
    pilot.TESTS = ["backend/tests/rolling_forecast"]
    original = pilot.command

    def command(arguments, environment, log, **kwargs):
        if arguments[:3] == ["npx", "playwright", "test"]:
            # Keep original S4 real-HTTPS regression, add S7 on both projects.
            arguments = [*arguments[:3], "rolling-forecast.spec.ts", *arguments[3:]]
        return original(arguments, environment, log, **kwargs)

    pilot.command = command
    pilot.main()


if __name__ == "__main__":
    main()
