#!/usr/bin/env python3
"""Collect a fresh TypeSafe key without displaying it or storing it in the repo."""

from __future__ import annotations

import getpass
import os
import sys
import tempfile
import warnings
from pathlib import Path


def main() -> int:
    if not sys.stdin.isatty():
        raise SystemExit("Run this from a private terminal; non-interactive key input is refused.")
    try:
        from typesafe_sdk import RetryPolicy, TypeSafeClient, __version__
    except ImportError as exc:
        raise SystemExit("Install the optional dependency first: pip install 'typesafe-sdk==0.7.2'") from exc
    if __version__ != "0.7.2":
        raise SystemExit(f"Expected typesafe-sdk 0.7.2, found {__version__}.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            key = getpass.getpass("Fresh TypeSafe API key (hidden input): ")
        except getpass.GetPassWarning as exc:
            raise SystemExit("This terminal cannot hide input; no key was read.") from exc
    if not key or key != key.strip() or "\n" in key or "\r" in key:
        raise SystemExit("Key input was empty or malformed; nothing was saved.")

    try:
        with TypeSafeClient(api_key=key, retry=RetryPolicy(max_retries=0), timeout=90) as client:
            inventory = client.models.list()
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        raise SystemExit(f"Key verification failed ({type(exc).__name__}, HTTP {status}); nothing was saved.") from exc
    names = {item.name for item in inventory.models}
    if "jev-latest" not in names:
        raise SystemExit("Authenticated inventory did not include Jev; nothing was saved.")

    destination = Path.home() / ".config/fleet-mem-contextbench/jev.env"
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(destination.parent, 0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".jev.env.tmp-", dir=destination.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write("TYPESAFE_API_KEY=" + _shell_quote(key) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f"Jev credential verified and stored outside the repository at {destination} (mode 600). Key value was not displayed.")
    return 0


def _shell_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)


if __name__ == "__main__":
    raise SystemExit(main())
