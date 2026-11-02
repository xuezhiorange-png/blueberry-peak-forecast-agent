"""Trusted workflow metadata only. Never discover trust from proposed files."""

import argparse
import json
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--test-merge")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    values = [args.base, args.head, *([args.test_merge] if args.test_merge else [])]
    if any(not re.fullmatch(r"[0-9a-f]{40}", value) for value in values):
        raise SystemExit("INVALID_TRUSTED_EVENT_IDENTITY")
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.expected_repository)
        or args.expected_repository == "xuezhiorange-png/blueberry-peak-forecast-agent"
    ):
        raise SystemExit("CLEAN_REMOTE_IDENTITY_REQUIRED")
    refs = [["refs/heads/trusted-base", args.base], ["refs/heads/proposed-head", args.head]]
    if args.test_merge:
        refs.append(["refs/heads/test-merge", args.test_merge])
    payload = {
        "base": args.base,
        "head": args.head,
        "checkout": args.test_merge or args.head,
        "refs": sorted(refs),
        "origin": "https://github.com/" + args.expected_repository,
        "test_merge": args.test_merge,
    }
    with args.output.open("xb") as output:
        args.output.chmod(0o600)
        output.write((json.dumps(payload, sort_keys=True, indent=2) + "\n").encode())


if __name__ == "__main__":
    main()
