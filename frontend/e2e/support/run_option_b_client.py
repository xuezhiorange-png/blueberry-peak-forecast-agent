"""Add the new client browser spec to the existing immutable S6/S5 runner."""

from backend.tests.acceptance_s6 import run as acceptance
from backend.tests.safe_pilot import run as owned


def main():
    original = owned.command

    def command(arguments, environment, log, **kwargs):
        if arguments[:3] == ["npx", "playwright", "test"]:
            arguments = [*arguments, "option-b-client-binding.spec.ts"]
        return original(arguments, environment, log, **kwargs)

    owned.command = command
    try:
        acceptance.main()
    finally:
        owned.command = original


if __name__ == "__main__":
    main()
