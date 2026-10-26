#!/usr/bin/env python3
"""
Score the original draw and the extension separately.

    python3 eval/04e_split_score.py

The merged sample mixes two draws made against different specs, and possibly
by two different labellers. If the tool's measured accuracy differs sharply
between them, the cause is one of:

  * the stratification. The original 99 were drawn when libpq had 122 refused
    functions; it now has 36. A "refused" stratum drawn then is not the same
    population as one drawn now.
  * the labeller. Two people applying label_should_bind can differ on where a
    callback stops being bindable, which is what the agreement sheets exist to
    measure.
  * genuine difficulty. A larger sample simply reaches further into each
    library's long tail.

The first two are measurement artifacts and must be reported as such; the
third is a real result. This script cannot separate them on its own, but it
tells you whether there is anything to separate.

Uses audit_<lib>_ext_blind.csv to identify extension rows and the
.pre_merge backups for the original ones.
"""
from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
import tempfile

AUDIT = "eval_output/audit"
LIBS = ["cjson", "sqlite", "zlib", "libpng", "libpq", "libgit2", "libxml2"]


def names_of(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="") as f:
        return {r["function"] for r in csv.DictReader(f)}


def subset(src, keep, dst):
    rows = [r for r in csv.DictReader(open(src, newline=""))
            if r["function"] in keep]
    if not rows:
        return None
    with open(dst, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader(); w.writerows(rows)
    return len(rows)


def run(pairs):
    out = subprocess.run([sys.executable, "eval/04b_tally_audit.py"] + pairs,
                         capture_output=True, text=True).stdout
    row = re.search(r"OVERALL\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", out)
    acc = re.search(r"accuracy\s+([\d.]+)%", out)
    if not row:
        return None, out
    return dict(n=int(row.group(1)), correct=int(row.group(2)),
                unsafe=int(row.group(3)), leak=int(row.group(4)),
                false_ref=int(row.group(5)), other=int(row.group(6)),
                acc=float(acc.group(1))), out


def main():
    tmp = tempfile.mkdtemp()
    groups = {"original": [], "extension": []}
    counts = {"original": 0, "extension": 0}

    for lib in LIBS:
        blind = f"{AUDIT}/audit_{lib}_blind.csv"
        key = f"{AUDIT}/audit_{lib}_key.csv"
        if not (os.path.exists(blind) and os.path.exists(key)):
            continue
        ext_names = names_of(f"{AUDIT}/audit_{lib}_ext_blind.csv")
        pre = f"{blind}.pre_merge"
        orig_names = names_of(pre) if os.path.exists(pre) else \
            (names_of(blind) - ext_names)

        for group, keep in (("original", orig_names), ("extension", ext_names)):
            if not keep:
                continue
            b = os.path.join(tmp, f"{group}_{lib}_blind.csv")
            k = os.path.join(tmp, f"{group}_{lib}_key.csv")
            nb, nk = subset(blind, keep, b), subset(key, keep, k)
            if nb and nk:
                groups[group] += ["--pairs", f"{b}:{k}"]
                counts[group] += nb

    print(f"\n{'draw':<12}{'n':>5}{'acc':>8}{'unsafe':>8}{'leak':>6}"
          f"{'f-ref':>7}{'other':>7}")
    res = {}
    for group in ("original", "extension"):
        if not groups[group]:
            print(f"  {group}: no rows")
            continue
        s, out = run(groups[group])
        if s is None:
            print(f"  {group}: scoring failed\n{out[:400]}")
            continue
        res[group] = s
        print(f"{group:<12}{s['n']:>5}{s['acc']:>7.1f}%{s['unsafe']:>8}"
              f"{s['leak']:>6}{s['false_ref']:>7}{s['other']:>7}")

    if len(res) == 2:
        o, e = res["original"], res["extension"]
        d = e["acc"] - o["acc"]
        print(f"\ndifference: {d:+.1f} points of accuracy, "
              f"{e['unsafe'] - o['unsafe']:+d} unsafe, "
              f"{e['false_ref'] - o['false_ref']:+d} false refusals")
        if abs(d) < 8:
            print("Small. The two draws measure the same thing; report the "
                  "pooled figure.")
        else:
            print("Large. Do not report the pooled figure without explaining "
                  "it.\nCheck, in this order: whether a different person "
                  "labelled the extension\n(the agreement sheets answer that), "
                  "and whether the extension's refused\nstratum is drawn from "
                  "a population the original could not reach.")

    print("\nper-library, extension only:")
    for lib in LIBS:
        b = os.path.join(tmp, f"extension_{lib}_blind.csv")
        k = os.path.join(tmp, f"extension_{lib}_key.csv")
        if not os.path.exists(b):
            continue
        s, _ = run(["--pairs", f"{b}:{k}"])
        if s:
            print(f"  {lib:<9} n={s['n']:<3} acc={s['acc']:>5.1f}%  "
                  f"unsafe={s['unsafe']}  leak={s['leak']}  "
                  f"f-ref={s['false_ref']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
