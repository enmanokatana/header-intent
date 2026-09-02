"""
Run the test-assertion extractor over one Unity test file or a whole tests/
directory and print the reusability classification, the headline number for
the paper's test-suite-reuse methodology (section 5).

    python3 -m ferrule.reuse.report <file.c | tests_dir/> [lib_prefix]

Example:
    python3 -m ferrule.reuse.report /tmp/cjson/tests cJSON
"""
import os
import sys

from .extract import extract_file, summarize


def _c_files(target: str) -> list[str]:
    if os.path.isfile(target):
        return [target]
    out = []
    for root, _dirs, files in os.walk(target):
        # skip the vendored Unity framework itself -- we classify the LIBRARY's
        # tests, not the test framework's own self-tests.
        if "unity" in root.split(os.sep):
            continue
        for fn in files:
            if fn.endswith(".c"):
                out.append(os.path.join(root, fn))
    return sorted(out)


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python3 -m ferrule.reuse.report <file.c|dir> [lib_prefix]")
        return 2
    target = argv[0]
    lib_prefix = argv[1] if len(argv) > 1 else "cJSON"

    files = _c_files(target)
    if not files:
        print(f"no .c files found under {target}")
        return 1

    grand = {"test_functions": 0, "assertions_total": 0,
             "assertions_reusable": 0, "assertions_blocked": 0}
    grand_reasons: dict[str, int] = {}
    per_file = []

    for path in files:
        tests = extract_file(path, lib_prefix=lib_prefix)
        s = summarize(tests)
        if s["assertions_total"] == 0:
            continue
        per_file.append((os.path.basename(path), s))
        for k in grand:
            grand[k] += s[k]
        for reason, n in s["blocked_reasons"].items():
            grand_reasons[reason] = grand_reasons.get(reason, 0) + n

    print(f"=== test-suite reusability report: {target} ===\n")
    print(f"{'file':32} {'tests':>6} {'assert':>7} {'reuse':>6} {'block':>6}")
    print("-" * 62)
    for name, s in per_file:
        print(f"{name:32} {s['test_functions']:>6} {s['assertions_total']:>7} "
              f"{s['assertions_reusable']:>6} {s['assertions_blocked']:>6}")
    print("-" * 62)
    print(f"{'TOTAL':32} {grand['test_functions']:>6} {grand['assertions_total']:>7} "
          f"{grand['assertions_reusable']:>6} {grand['assertions_blocked']:>6}")

    total = grand["assertions_total"]
    if total:
        pct = 100.0 * grand["assertions_reusable"] / total
        print(f"\nmechanically reusable: {grand['assertions_reusable']}/{total} "
              f"({pct:.1f}%) of assertions")
    print("\nwhy the rest are blocked:")
    for reason, n in sorted(grand_reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
