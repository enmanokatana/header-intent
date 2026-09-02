"""
Read one or more filled-in audit CSVs (from 03_sample_audit.py) and compute the
generalization numbers for the paper: per library and overall, the correctness
rate and the safe-vs-unsafe split of the errors.

Usage:
    python3 04_tally_audit.py audit_zlib.csv audit_libcurl.csv audit_libgit2.csv
"""
import csv
import sys
from collections import defaultdict


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 04_tally_audit.py <audit1.csv> [audit2.csv ...]")

    overall = defaultdict(int)
    print(f"{'library':16} {'n':>4} {'correct':>8} {'acc%':>6} "
          f"{'safe-err':>9} {'unsafe-err':>11}")
    print("-" * 60)

    for path in sys.argv[1:]:
        n = correct = safe = unsafe = blank = 0
        with open(path) as f:
            for row in csv.DictReader(f):
                vc = (row.get("verdict_correct(y/n)") or "").strip().lower()
                ed = (row.get("error_direction(safe/unsafe)") or "").strip().lower()
                if vc not in ("y", "n"):
                    blank += 1
                    continue
                n += 1
                if vc == "y":
                    correct += 1
                else:
                    if ed == "safe":
                        safe += 1
                    elif ed == "unsafe":
                        unsafe += 1
        lib = path.replace("audit_", "").replace(".csv", "")
        acc = (100.0 * correct / n) if n else 0.0
        print(f"{lib:16} {n:>4} {correct:>8} {acc:>5.1f}% {safe:>9} {unsafe:>11}"
              + (f"   ({blank} unreviewed)" if blank else ""))
        overall["n"] += n; overall["correct"] += correct
        overall["safe"] += safe; overall["unsafe"] += unsafe

    print("-" * 60)
    n = overall["n"]; c = overall["correct"]
    acc = (100.0 * c / n) if n else 0.0
    print(f"{'OVERALL':16} {n:>4} {c:>8} {acc:>5.1f}% "
          f"{overall['safe']:>9} {overall['unsafe']:>11}")
    print()
    if n:
        errs = overall["safe"] + overall["unsafe"]
        if errs:
            print(f"Of {errs} errors, {overall['safe']} ({100.0*overall['safe']/errs:.0f}%) "
                  f"were safe-side, {overall['unsafe']} "
                  f"({100.0*overall['unsafe']/errs:.0f}%) unsafe-side.")
        print(f"This is the sentence the paper wants: across held-out libraries, "
              f"{acc:.1f}% of verdicts correct, and errors skewed "
              f"{'safe' if overall['safe']>=overall['unsafe'] else 'UNSAFE (!)'}.")


if __name__ == "__main__":
    main()
