"""Offline checks for lit_fetch.py. Plain asserts, no test framework.

Run: python test_lit_fetch.py   (exit 0 when all checks pass)
Network calls never leave the test process: every test that reaches the
network installs a fake via lit_fetch.http_get (see Task 3).
"""

import sys

import lit_fetch

CHECKS = []


def main():
    failed = 0
    for check in CHECKS:
        try:
            check()
            print("PASS " + check.__name__)
        except Exception as exc:
            failed += 1
            print("FAIL " + check.__name__ + ": "
                  + exc.__class__.__name__ + ": " + str(exc))
    if failed:
        print(str(failed) + " check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
