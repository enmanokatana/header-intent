"""
Draw a random, reproducible sample of BOUND functions from a generated spec and
emit a CSV audit sheet for manual blind review. This produces the paper's
headline generalization number: of a held-out library's bound functions, how
many ownership/lifecycle verdicts are correct, and of the errors, how many fall
on the SAFE (conservative) side vs the UNSAFE side.

Usage:
    python3 03_sample_audit.py <spec.yaml> [--n 30] [--seed 1] > audit_<lib>.csv

Then open the CSV, and for each row fill:
    verdict_correct : y / n
    error_direction : (blank if correct) / safe / unsafe
    notes           : free text

"safe" error  = tool was too conservative (refused-worthy call marked borrowed,
                 or a real owner marked borrowed) -> leaks at worst.
"unsafe" error = tool marked something owned/free-able that is actually borrowed
                 or must not be freed -> double-free / UAF risk. THIS is the
                 number that must stay near zero for the fail-safe claim.
"""
import argparse
import csv
import random
import sys

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    with open(args.spec) as f:
        spec = yaml.safe_load(f)

    funcs = spec.get("functions", {}) or {}
    # a "bound" function is one that wasn't refused; the spec only contains
    # functions the pipeline kept, but we surface lifecycle/owner for audit.
    rows = []
    for name, fn in funcs.items():
        rows.append({
            "function": name,
            "lifecycle": fn.get("lifecycle", ""),
            "owner": fn.get("owner", ""),
            "handle_type": fn.get("handle_type", ""),
            "ret": (fn.get("restype") or ""),
        })

    if not rows:
        sys.exit(f"no functions found in {args.spec} (all refused, or wrong file?)")

    random.seed(args.seed)
    sample = random.sample(rows, min(args.n, len(rows)))
    sample.sort(key=lambda r: r["function"])

    w = csv.writer(sys.stdout)
    w.writerow(["function", "lifecycle", "owner", "handle_type", "ret",
                "verdict_correct(y/n)", "error_direction(safe/unsafe)", "notes"])
    for r in sample:
        w.writerow([r["function"], r["lifecycle"], r["owner"],
                    r["handle_type"], r["ret"], "", "", ""])

    print(f"# sampled {len(sample)} of {len(rows)} bound functions "
          f"from {args.spec} (seed={args.seed})", file=sys.stderr)


if __name__ == "__main__":
    main()
