"""Run the WP-FX01 fixed-fixture demo with ``python -m mishi_radar.demo``."""

from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Mishi Radar WP-FX01 fixed-fixture demo")
    parser.add_argument("--host", default=os.environ.get("MISHI_DEMO_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MISHI_DEMO_PORT", "8000")))
    args = parser.parse_args()
    uvicorn.run("mishi_radar.demo.app:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
