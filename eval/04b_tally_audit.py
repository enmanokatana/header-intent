"""
Score hand-labelled audit sheets against Ferrule's verdicts.  (fix F12)

Produces the four numbers RQ0 needs, per library and pooled:

    correct        ownership AND lifecycle verdicts both match the label
    unsafe         the verdict PERMITS something the label forbids:
                     - ferrule says owner=caller, label says library   (double free)
                     - ferrule says destroys, label says it does not   (use after free)
                     - ferrule BOUND a function the label says must not be exposed
    leak           ferrule says owner=library, label says caller       (missed free)
    false_refuse   ferrule refused a function the label says is safe to expose

and, when a second annotator's sheet is present, Cohen's kappa on the three label
fields.

Usage
-----
    python3 04b_tally_audit.py --pairs audit_cjson_blind.csv:audit_cjson_key.csv \\
                               --pairs audit_libpq_blind.csv:audit_libpq_key.csv \\
                               --kappa audit_cjson_blind.csv:audit_cjson_blind_annotator2.csv \\
                               --latex accuracy_table.tex --numbers numbers.tex
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict


def read(path):
    with open(path, newline="") as f:
        return {r["function"]: r for r in csv.DictReader(f)}


def norm(s):
    return (s or "").strip().lower()


def score_one(labels, key):
    """Return (per-row verdicts, counters)."""
    c = Counter()
    rows = []
    for name, lab in labels.items():
        k = key.get(name)
        if k is None:
            continue
        lo, ll = norm(lab["label_owner"]), norm(lab["label_lifecycle"])
        should = norm(lab["label_should_bind"])
        if not lo and not ll and not should:
            c["unlabelled"] += 1
            continue
        fo, fl = norm(k["ferrule_owner"]), norm(k["ferrule_lifecycle"])
        bound = norm(k["ferrule_bound"]) == "y"

        verdict = "correct"
        # --- safety-relevant disagreements first -------------------------------
        if bound and should == "n":
            verdict = "unsafe"                      # exposed something unexposable
        elif bound and fo == "caller" and lo == "library":
            verdict = "unsafe"                      # permits a double free
        elif bound and fl == "destroys" and ll not in ("destroys", ""):
            verdict = "unsafe"                      # releases a live handle
        elif bound and fo == "library" and lo == "caller":
            verdict = "leak"                        # conservative, forgoes a free
        elif not bound and should == "y":
            verdict = "false_refuse"
        elif bound and ((lo and fo and lo != fo) or (ll and fl and ll != fl)):
            verdict = "wrong_other"
        elif not bound and should == "n":
            verdict = "correct"                     # correctly refused
        c[verdict] += 1
        c["n"] += 1
        c[f"stratum::{lab.get('stratum','?')}::{verdict}"] += 1
        rows.append((name, verdict, fo, lo, fl, ll, bound, should))
    return rows, c


def kappa(a, b, fields=("label_owner", "label_lifecycle", "label_should_bind")):
    """Cohen's kappa pooled over the label fields for rows both annotators did."""
    obs = tot = 0
    marg_a, marg_b = Counter(), Counter()
    for name, ra in a.items():
        rb = b.get(name)
        if rb is None:
            continue
        for f in fields:
            va, vb = norm(ra.get(f)), norm(rb.get(f))
            if not va or not vb:
                continue
            tot += 1
            obs += (va == vb)
            marg_a[va] += 1
            marg_b[vb] += 1
    if not tot:
        return None, 0
    po = obs / tot
    pe = sum((marg_a[k] / tot) * (marg_b[k] / tot) for k in set(marg_a) | set(marg_b))
    if pe == 1.0:
        return 1.0, tot
    return (po - pe) / (1 - pe), tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", action="append", required=True,
                    metavar="BLIND.csv:KEY.csv")
    ap.add_argument("--kappa", action="append", default=[],
                    metavar="ANNOT1.csv:ANNOT2.csv")
    ap.add_argument("--latex")
    ap.add_argument("--numbers", help="write \\newcommand definitions for the paper")
    args = ap.parse_args()

    totals = Counter()
    lines = []
    print(f"{'library':12} {'n':>4} {'correct':>8} {'unsafe':>7} {'leak':>6} "
          f"{'false-ref':>10} {'other':>6}")
    print("-" * 60)
    for pair in args.pairs:
        bl, ky = pair.split(":")
        rows, c = score_one(read(bl), read(ky))
        lib = bl.replace("audit_", "").replace("_blind.csv", "")
        print(f"{lib:12} {c['n']:>4} {c['correct']:>8} {c['unsafe']:>7} {c['leak']:>6} "
              f"{c['false_refuse']:>10} {c['wrong_other']:>6}"
              + (f"   ({c['unlabelled']} unlabelled)" if c["unlabelled"] else ""))
        lines.append((lib, c))
        for k, v in c.items():
            if not k.startswith("stratum::"):
                totals[k] += v
        for name, verdict, fo, lo, fl, ll, bound, should in rows:
            if verdict in ("unsafe", "leak"):
                print(f"    [{verdict:6}] {name}: ferrule owner={fo or '-'} "
                      f"lifecycle={fl or '-'} | label owner={lo or '-'} "
                      f"lifecycle={ll or '-'}")
    print("-" * 60)
    n = totals["n"] or 1
    print(f"{'OVERALL':12} {totals['n']:>4} {totals['correct']:>8} {totals['unsafe']:>7} "
          f"{totals['leak']:>6} {totals['false_refuse']:>10} {totals['wrong_other']:>6}")
    print(f"\naccuracy {100.0*totals['correct']/n:.1f}%   "
          f"unsafe {100.0*totals['unsafe']/n:.1f}%   "
          f"leak {100.0*totals['leak']/n:.1f}%   "
          f"false-refuse {100.0*totals['false_refuse']/n:.1f}%")

    kv, kn = None, 0
    for pair in args.kappa:
        a, b = pair.split(":")
        kv, kn = kappa(read(a), read(b))
        print(f"inter-annotator agreement on {kn} field comparisons: kappa = {kv:.2f}")

    if args.latex:
        with open(args.latex, "w") as f:
            for lib, c in lines:
                f.write(f"{lib} & {c['n']} & {c['correct']} & {c['unsafe']} & "
                        f"{c['leak']} & {c['false_refuse']} \\\\\n")
            f.write("\\midrule\n")
            f.write(f"\\textbf{{Overall}} & {totals['n']} & {totals['correct']} & "
                    f"{totals['unsafe']} & {totals['leak']} & {totals['false_refuse']} \\\\\n")
        print(f"\nwrote {args.latex}")

    if args.numbers:
        with open(args.numbers, "w") as f:
            f.write(f"\\newcommand{{\\gtN}}{{{totals['n']}}}\n")
            f.write(f"\\newcommand{{\\gtAcc}}{{{100.0*totals['correct']/n:.0f}\\%}}\n")
            f.write(f"\\newcommand{{\\gtUnsafe}}{{{totals['unsafe']}}}\n")
            f.write(f"\\newcommand{{\\gtSafe}}{{{totals['leak']}}}\n")
            f.write(f"\\newcommand{{\\gtFalseRefuse}}{{{totals['false_refuse']}}}\n")
            if kv is not None:
                f.write(f"\\newcommand{{\\kappaVal}}{{{kv:.2f}}}\n")
                f.write(f"\\newcommand{{\\kappaN}}{{{kn}}}\n")
        print(f"wrote {args.numbers}")


if __name__ == "__main__":
    main()
