#!/usr/bin/env python3
"""
Check returned label sheets before anything is merged or scored.

    python3 eval/04d_check_sheets.py                # report only
    python3 eval/04d_check_sheets.py --fix          # normalise safe variants

A label of "n/a" instead of "na", or "Y" instead of "y", scores as a mismatch.
That silently lowers kappa and the accuracy figure for a reason that has
nothing to do with the task, so the sheets get checked before they are used.

Blanks are legitimate -- the guide tells the annotator to leave a cell empty
rather than guess -- and are reported, not flagged. --fix only touches
case, surrounding whitespace, and unambiguous spellings of the same value
(n/a, N/A, none -> na; yes -> y; no -> n). It never invents a label.
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
from collections import Counter

AUDIT = "eval_output/audit"
VALID = {
    "label_owner": {"caller", "library", "shared", "na"},
    "label_lifecycle": {"creates", "uses", "destroys", "na"},
    "label_should_bind": {"y", "n"},
    "label_source": {"doc", "source", "both"},
}
ALIASES = {
    "n/a": "na", "na.": "na", "none": "na", "-": "na", "unknown": "",
    "yes": "y", "no": "n", "true": "y", "false": "n",
    "create": "creates", "use": "uses", "destroy": "destroys",
    "docs": "doc", "src": "source", "code": "source",
}


def norm(v):
    s = (v or "").strip().lower()
    return ALIASES.get(s, s)


def check(path, fix):
    rows = list(csv.DictReader(open(path, newline="")))
    if not rows:
        return None
    issues, changed = [], 0
    labelled = 0
    blanks = Counter()
    for i, r in enumerate(rows, 2):
        any_label = False
        for col, ok in VALID.items():
            if col not in r:
                continue
            raw = r[col]
            v = norm(raw)
            if v and v != (raw or "").strip():
                changed += 1
                if fix:
                    r[col] = v
            if not v:
                blanks[col] += 1
                continue
            any_label = True
            if v not in ok:
                issues.append(f"    line {i}  {r['function']}: "
                              f"{col}={raw!r} (expected one of {sorted(ok)})")
        if any_label:
            labelled += 1
    if fix and (changed or issues):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader(); w.writerows(rows)
    return dict(n=len(rows), labelled=labelled, issues=issues,
                changed=changed, blanks=blanks,
                names={r["function"] for r in rows})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", default=AUDIT)
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()

    groups = {"main": "_blind.csv", "extension": "_ext_blind.csv",
              "annotator2": "_blind_annotator2.csv"}
    seen = {}
    for label, suffix in groups.items():
        paths = sorted(p for p in glob.glob(f"{args.audit}/audit_*{suffix}")
                       if not any(p.endswith(s) for s in
                                  (groups["extension"], groups["annotator2"]))
                       or suffix != groups["main"])
        if not paths:
            continue
        print(f"\n{label.upper()}")
        for p in paths:
            lib = re.search(r"audit_(\w+?)(_ext)?_blind", os.path.basename(p)).group(1)
            r = check(p, args.fix)
            if r is None:
                print(f"  {lib:<9} EMPTY")
                continue
            seen.setdefault(label, {})[lib] = r
            b = " ".join(f"{k.replace('label_',''):.4}={v}"
                         for k, v in sorted(r["blanks"].items()) if v)
            print(f"  {lib:<9} {r['labelled']:>3}/{r['n']:<3} labelled"
                  + (f"   blanks: {b}" if b else "")
                  + (f"   [{r['changed']} normalised]" if r["changed"] and args.fix else "")
                  + (f"   [{r['changed']} need --fix]" if r["changed"] and not args.fix else ""))
            for line in r["issues"]:
                print(line)

    # cross-checks
    print("\nCROSS-CHECKS")
    for lib, m in seen.get("main", {}).items():
        a2 = seen.get("annotator2", {}).get(lib)
        if a2:
            extra = a2["names"] - m["names"]
            print(f"  {lib:<9} annotator2 {len(a2['names'])} rows, "
                  + ("all present in the main sheet"
                     if not extra else f"!! {len(extra)} not in main: "
                                       f"{sorted(extra)[:3]}"))
        ext = seen.get("extension", {}).get(lib)
        if ext:
            overlap = ext["names"] & m["names"]
            print(f"  {lib:<9} extension  {len(ext['names'])} rows, "
                  + ("no overlap with the main sheet"
                     if not overlap else f"!! {len(overlap)} overlap: "
                                         f"{sorted(overlap)[:3]}"))

    ready_ext = all(r["labelled"] == r["n"]
                    for r in seen.get("extension", {}).values())
    ready_a2 = all(r["labelled"] == r["n"]
                   for r in seen.get("annotator2", {}).values())
    print("\nNEXT")
    if seen.get("annotator2") and ready_a2:
        libs = sorted(seen["annotator2"])
        print("  agreement is ready:")
        print("    python3 eval/04b_tally_audit.py \\")
        print("        " + " \\\n        ".join(
            f"--pairs {args.audit}/audit_{l}_blind.csv:{args.audit}/audit_{l}_key.csv"
            for l in libs))
        print("        " + " \\\n        ".join(
            f"--kappa {args.audit}/audit_{l}_blind.csv:"
            f"{args.audit}/audit_{l}_blind_annotator2.csv" for l in libs))
    elif seen.get("annotator2"):
        print("  agreement sheets still have unlabelled rows")
    if seen.get("extension") and ready_ext:
        print("  extension is ready to merge:")
        print("    python3 eval/03c_extend_audit.py --repo . --merge")
        print("    python3 eval/04c_rekey_audit.py  --repo . --snapshots snapshots")
    elif seen.get("extension"):
        print("  extension sheets still have unlabelled rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
