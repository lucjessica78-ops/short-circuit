#!/usr/bin/env python3
"""
PandaSC license key generator -- FOR YOUR EYES ONLY.

Run this yourself whenever you sell a copy of PandaSC. It uses the same
SECRET as backend/license_manager.py to mint a key the app can validate
completely offline (no server, no internet check).

Keep this script private:
  - Do not commit it to a public repo.
  - Do not include it in the PyInstaller build (build.spec already excludes it).
  - If you ever suspect SECRET has leaked, change SECRET in BOTH this file
    and backend/license_manager.py, then rebuild the app -- old keys will
    stop validating and you'll need to reissue them to existing customers.

Usage:
  python keygen.py                     # one perpetual key
  python keygen.py --days 30           # one key valid for 30 days
  python keygen.py --count 5           # five perpetual keys
  python keygen.py --note "Acme Corp"  # just a label for your own records
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import license_manager as lm  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="Generate PandaSC license keys.")
    p.add_argument("--days", type=int, default=None, help="Days until expiry (omit for a perpetual key).")
    p.add_argument("--count", type=int, default=1, help="How many keys to generate.")
    p.add_argument("--note", type=str, default=None, help="A label for your own records (not encoded in the key).")
    args = p.parse_args()

    for _ in range(args.count):
        key = lm.generate_key(days_valid=args.days)
        line = key
        if args.note:
            line += f"    ({args.note})"
        print(line)


if __name__ == "__main__":
    main()
