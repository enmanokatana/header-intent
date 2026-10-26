#!/usr/bin/env python3
"""
Extend the ground-truth sample against the frozen specs.

    # draw the extension, and an agreement sheet for the existing 99
    python3 eval/03c_extend_audit.py --repo . --per-stratum 5 \\
        --seed 20260924 --second-annotator 40

    # after the extension sheets come back labelled
    python3 eval/03c_extend_audit.py --repo . --merge

Why extend rather than redraw. The existing 99 were stratified against the
specs as they stood before this session, including a "refused" stratum --
and libpq's refused set fell from 122 to 36. The labels remain valid, since
they describe the libraries rather than the tool, but the stratification no
longer matches the system being measured. Drawing a second sample against the
frozen specs fixes that without discarding labelling effort, and comparing
accuracy across the two draws is itself a check: a sharp divergence would mean
the stale stratification mattered.

Two things this buys, which are independent:

  * A tighter bound on the unsafe rate. One unsafe verdict in 99 gives a
    Wilson upper bound of 5.5%; two in 200 gives 3.6%. That upper bound is
    the number a safety-focused reader weighs.
  * libxml2 enters the accuracy measurement. It contributes 474 bindings to
    coverage and nothing to correctness at present. Labelling it does not
    compromise its blind status, which concerns the ANALYSIS never having
    been adapted to it, not the labels.

Cohen's kappa does NOT need a larger sample -- it needs a second rater. The
--second-annotator sheet is therefore drawn from the sample that is already
labelled, so agreement can be measured without waiting for the extension.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import random
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
STRATA = ("handle_return", "lifecycle", "refused", "other")


def load_03b(repo):
    p = os.path.join(repo, "eval", "03b_sample_audit.py")
    spec = importlib.util.spec_from_file_location("s03b", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def read_names(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="") as f:
        return {r["function"] for r in csv.DictReader(f)}


def do_merge(args):
    """Fold labelled extension rows into the main sheets."""
    for lib in SO:
        for kind in ("blind", "key"):
            main = f"{args.audit}/audit_{lib}_{kind}.csv"
            ext = f"{args.audit}/audit_{lib}_ext_{kind}.csv"
            if not os.path.exists(ext):
                continue
            rows_ext = list(csv.DictReader(open(ext, newline="")))
            if kind == "blind":
                unlabelled = [r["function"] for r in rows_ext
                              if not (r.get("label_owner") or "").strip()]
                if unlabelled:
                    print(f"  ! {lib}: {len(unlabelled)} extension rows still "
                          f"unlabelled, skipping merge")
                    break
            if os.path.exists(main):
                rows_main = list(csv.DictReader(open(main, newline="")))
                if not os.path.exists(main + ".pre_merge"):
                    os.replace(main, main + ".pre_merge")
                    rows_main = list(csv.DictReader(
                        open(main + ".pre_merge", newline="")))
            else:
                rows_main = []
            have = {r["function"] for r in rows_main}
            added = [r for r in rows_ext if r["function"] not in have]
            allrows = rows_main + added
            allrows.sort(key=lambda r: r["function"])
            with open(main, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=rows_ext[0].keys())
                w.writeheader(); w.writerows(allrows)
            print(f"  {lib:<9} {kind:<5} {len(rows_main)} + {len(added)} "
                  f"= {len(allrows)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--snapshots", default="snapshots")
    ap.add_argument("--audit", default="eval_output/audit")
    ap.add_argument("--suffix", default="audit")
    ap.add_argument("--libs-root", default=os.path.expanduser("~/ferrule-libs"))
    ap.add_argument("--per-stratum", type=int, default=5)
    ap.add_argument("--seed", type=int, default=20260924)
    ap.add_argument("--second-annotator", type=int, default=0,
                    help="rows to draw from the ALREADY LABELLED sample for kappa")
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()

    if args.merge:
        return do_merge(args)

    m = load_03b(args.repo)
    total_new = 0
    for lib, so_rel in SO.items():
        spec_p = f"{args.snapshots}/{lib}_{args.suffix}.yaml"
        so_p = os.path.join(args.libs_root, so_rel)
        if not (os.path.exists(spec_p) and os.path.exists(so_p)):
            print(f"  ! {lib}: missing {spec_p} or {so_p}")
            continue
        blind_p = f"{args.audit}/audit_{lib}_blind.csv"
        already = read_names(blind_p)

        table = m.load(args.repo, spec_p, so_p)
        buckets = {}
        for name, (fn, bound, reason) in table.items():
            if name in already:
                continue
            buckets.setdefault(m.stratum_of(name, fn, bound), []).append(
                (name, fn, bound, reason))

        random.seed(args.seed + sum(ord(c) for c in lib))
        sample = []
        for s in STRATA:
            rows = buckets.get(s, [])
            sample.extend((s, *r) for r in
                          random.sample(rows, min(args.per_stratum, len(rows))))
        sample.sort(key=lambda r: r[1])
        if not sample:
            print(f"  {lib:<9} nothing left to draw")
            continue

        with open(f"{args.audit}/audit_{lib}_ext_blind.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(m.BLIND_COLS)
            for s, name, fn, bound, reason in sample:
                w.writerow([name, m.signature_of(fn), s, "", "", "", "", ""])
        with open(f"{args.audit}/audit_{lib}_ext_key.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(m.KEY_COLS)
            for s, name, fn, bound, reason in sample:
                w.writerow([name, s, fn.owner or "", fn.lifecycle or "",
                            "y" if bound else "n", reason])

        avail = {s: len(buckets.get(s, [])) for s in STRATA}
        drew = {s: sum(1 for r in sample if r[0] == s) for s in STRATA}
        total_new += len(sample)
        print(f"  {lib:<9} +{len(sample):<3} "
              + "  ".join(f"{s[:4]}={drew[s]}/{avail[s]}" for s in STRATA)
              + (f"   ({len(already)} already labelled)" if already else "   (new library)"))

    print(f"\n{total_new} new rows -> audit_<lib>_ext_blind.csv")

    if args.second_annotator:
        print("\nagreement sheets, drawn from the already-labelled sample:")
        for lib in SO:
            blind_p = f"{args.audit}/audit_{lib}_blind.csv"
            if not os.path.exists(blind_p):
                continue
            rows = [r for r in csv.DictReader(open(blind_p, newline=""))
                    if (r.get("label_owner") or "").strip()]
            if not rows:
                continue
            random.seed(args.seed)
            take = random.sample(rows, min(args.second_annotator, len(rows)))
            take.sort(key=lambda r: r["function"])
            p = f"{args.audit}/audit_{lib}_blind_annotator2.csv"
            with open(p, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=rows[0].keys())
                w.writeheader()
                for r in take:
                    w.writerow({k: ("" if k.startswith("label") or k == "notes"
                                    else v) for k, v in r.items()})
            print(f"  {lib:<9} {len(take)} rows -> {os.path.basename(p)}")

    print("""
Hand over in one go: the audit_<lib>_ext_blind.csv sheets to label, and the
audit_<lib>_blind_annotator2.csv sheets for the agreement measurement. Then:

    python3 eval/03c_extend_audit.py --repo . --merge
    python3 eval/04c_rekey_audit.py  --repo . --snapshots snapshots
    python3 eval/04b_tally_audit.py --pairs ... --kappa ...""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
