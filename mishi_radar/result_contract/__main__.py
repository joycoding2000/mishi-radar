"""Emit a deterministic WP-FX01A result contract bundle as JSON."""

from __future__ import annotations

import argparse
from pathlib import Path

from .adapter import build_result_bundle, dumps
from .fixtures import SCENARIOS


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a fixed SYNTHETIC F1/F3/F7 result bundle.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="normal")
    parser.add_argument("--strategy", choices=[f"S{index:02d}" for index in range(1, 9)], default="S01")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--security-id", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    payload = build_result_bundle(
        args.scenario,
        strategy_id=args.strategy,
        top_n=args.top_n,
        security_id=args.security_id,
    )
    text = dumps(payload) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
