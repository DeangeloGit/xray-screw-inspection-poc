"""Run the selected synthetic regression suites on Windows and macOS."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
# Isolated unittest discovery also rejects empty suites on older Python versions.
RUN_SUITE = """import sys, unittest
suite = unittest.defaultTestLoader.discover(sys.argv[1], pattern=sys.argv[2])
if suite.countTestCases() == 0:
    print('ERROR: no tests found', file=sys.stderr)
    sys.exit(1)
result = unittest.TextTestRunner().run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
"""
SUITES = (
    ("6R synthetic", ("tests", "test_*6r.py")),
    ("5R local object", ("tools", "test_local_object5r.py")),
    ("5R lost difference", ("tools", "test_lost_difference_shadow5r.py")),
    ("5R structure cause", ("tools", "test_structure_cause_shadow5r.py")),
    ("5R OK reference", ("tools", "test_ok_reference_shadow5r.py")),
)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    failures = []
    for name, arguments in SUITES:
        command = [sys.executable, "-B", "-c", RUN_SUITE, *arguments]
        print(f"\n=== {name} ===", flush=True)
        print("argv: " + json.dumps(command, ensure_ascii=True), flush=True)
        try:
            result = subprocess.run(command, cwd=ROOT, check=False)
            code = result.returncode
        except OSError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            code = 1
        print(f"{name}: exit {code}", flush=True)
        if code != 0:
            failures.append(name)
    if failures:
        print("\nFAILED: " + ", ".join(failures), flush=True)
        return 1
    print(f"\nPASS: all {len(SUITES)} selected synthetic suites passed.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
