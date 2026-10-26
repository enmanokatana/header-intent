#!/usr/bin/env python3
"""
Regenerate audit KEY sheets for the sample that already exists.

    python3 eval/04c_rekey_audit.py --repo . --snapshots snapshots \\
        --audit eval_output/audit --suffix audit

03b_sample_audit.py draws a fresh stratified sample every time it runs. Re-running
it now would produce different rows and orphan the 99 hand labels, which are tied
to those exact function names. The labels describe the LIBRARIES, not Ferrule, so
they stay valid across tool changes -- only the key side needs rebuilding.

This reads each audit_<lib>_blind.csv, looks every function up in the new spec via
03b's own load() (so `bound` means BUILT, through build_capabilities and the real
policy, not merely passing check_exposable), and rewrites audit_<lib>_key.csv with
the same columns. The blind sheets and the annotator2 sheets are never touched.

Old keys are saved as audit_<lib>_key.csv.bak once.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import shutil
import sys

SO = {
    "cjson": "cJSON/build/libcjson.so",
    "sqlite": "sqlite/libsqlite3.so",
    "zlib": "zlib/libz.so",
    "libpng": "libpng/.libs/libpng16.so",
    "libpq": "postgresql/src/interfaces/libpq/libpq.so",
    "libgit2": "libgit2/build/libgit2.so",
    "libxml2": "libxml2/build/libxml2.so",
}
COLS = ["function", "stratum", "ferrule_owner", "ferrule_lifecycle",
        "ferrule_bound", "refusal_reason"]


def load_03b(repo):
    path = os.path.join(repo, "eval", "03b_sample_audit.py")
    spec = importlib.util.spec_from_file_location("sampler03b", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--snapshots", default="snapshots")
    ap.add_argument("--audit", default="eval_output/audit")
    ap.add_argument("--suffix", default="audit")
    ap.add_argument("--libs-root", default=os.path.expanduser("~/ferrule-libs"))
    args = ap.parse_args()

    mod = load_03b(args.repo)
    total_changed = 0

    for lib, so_rel in SO.items():
        blind = os.path.join(args.audit, f"audit_{lib}_blind.csv")
        key = os.path.join(args.audit, f"audit_{lib}_key.csv")
        spec_p = os.path.join(args.snapshots, f"{lib}_{args.suffix}.yaml")
        so_p = os.path.join(args.libs_root, so_rel)
        if not os.path.exists(blind):
            continue
        if not (os.path.exists(spec_p) and os.path.exists(so_p)):
            print(f"  ! {lib}: missing {spec_p} or {so_p}, key left alone")
            continue

        table = mod.load(args.repo, spec_p, so_p)
        old = {}
        if os.path.exists(key):
            with open(key, newline="") as f:
                old = {r["function"]: r for r in csv.DictReader(f)}
            if not os.path.exists(key + ".bak"):
                shutil.copy(key, key + ".bak")

        rows, changed, missing = [], 0, 0
        with open(blind, newline="") as f:
            for r in csv.DictReader(f):
                name = r["function"]
                entry = table.get(name)
                if entry is None:
                    missing += 1
                    rows.append({"function": name,
                                 "stratum": r.get("stratum", ""),
                                 "ferrule_owner": "", "ferrule_lifecycle": "",
                                 "ferrule_bound": "",
                                 "refusal_reason": "not in spec"})
                    continue
                fn, bound, reason = entry
                row = {
                    "function": name,
                    "stratum": r.get("stratum", ""),
                    "ferrule_owner": fn.owner or "",
                    "ferrule_lifecycle": fn.lifecycle or "",
                    "ferrule_bound": "y" if bound else "n",
                    "refusal_reason": "" if bound else (reason or ""),
                }
                o = old.get(name)
                if o and any((o.get(c) or "") != (row[c] or "")
                             for c in ("ferrule_owner", "ferrule_lifecycle",
                                       "ferrule_bound")):
                    changed += 1
                    print(f"    {lib} {name}: "
                          f"{o.get('ferrule_owner')}/{o.get('ferrule_lifecycle')}"
                          f"/{o.get('ferrule_bound')}  ->  "
                          f"{row['ferrule_owner']}/{row['ferrule_lifecycle']}"
                          f"/{row['ferrule_bound']}")
                rows.append(row)

        with open(key, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            w.writerows(rows)
        total_changed += changed
        print(f"  {lib:<9} {len(rows):>3} rows, {changed} verdicts moved"
              + (f", {missing} not in spec" if missing else ""))

    print(f"\n{total_changed} verdicts moved in total. Now rescore:")
    print("  python3 eval/04b_tally_audit.py \\")
    print("      " + " \\\n      ".join(
        f"--pairs {args.audit}/audit_{l}_blind.csv:{args.audit}/audit_{l}_key.csv"
        for l in SO if os.path.exists(os.path.join(args.audit,
                                                   f"audit_{l}_blind.csv")))
        + " \\\n      --latex snapshots/table_accuracy.tex "
          "--numbers snapshots/accuracy_numbers.tex")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
