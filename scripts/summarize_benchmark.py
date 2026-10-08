#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the deterministic smoke screen summary.")
    parser.add_argument("--summary", default="artifacts/smoke/summary.json")
    args = parser.parse_args()
    value = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
