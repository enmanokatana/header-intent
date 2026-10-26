#!/usr/bin/env python3
"""
Reconcile the accuracy audit: every labelled function gets exactly ONE category.

    python3 eval/08_reconcile_audit.py              # summary + per-draw tables
    python3 eval/08_reconcile_audit.py --rows       # also list every non-correct row
    python3 eval/08_reconcile_audit.py --csv out.csv  # one line per function (artifact)

Why this exists
---------------
Table IV implies 77 incorrect verdicts (18 in the original draw, 59 in the
extension), but Table III names only 57 (1 unsafe + 5 exposability + 15 leak
+ 36 false refusals). The rest were an "other" column in 04b_tally_audit.py
that the paper stopped reporting. This script makes the categories mutually
exclusive, applies them in a fixed order, and prints counts that sum to n.

It also separates the two lifecycle error directions, which have opposite
consequences under the runtime:

  * FALSE destroys (verdict destroys, label not): the runtime calls the C
    function, which frees nothing, then drops the handle from the table.
    Result: the object leaks and later calls are refused. Not a memory error.
  * MISSED destroys (label destroys, verdict not): the C function frees the
    object, but the table keeps serving the handle. The next call through it
    is a use-after-free. This is the memory-unsafe direction.

04f counted the first as memory-unsafe and did not count the second at all.
CHECK the claim above against the CURRENT runtime before using it in the
paper: it rests on invoke() calling the C function and then handles.pop(),
with no runtime-side free and no teardown that calls a destructor.

Category precedence (first match wins)
--------------------------------------
Refused functions (ferrule_bound = n):
  R1 correct_refusal      label_should_bind = n
  R2 false_refusal        label_should_bind = y
Bound functions (ferrule_bound = y):
  B1 unsafe_owner         owner=caller, label says library/shared   -> double free
  B2 unsafe_missed_destroy label=destroys, verdict is not           -> use after free
  B3 exposability         label_should_bind = n                      -> no memory consequence
  B4 false_destroy        verdict=destroys, label is not             -> leak + handle lost
  B5 leak                 owner=library/unknown, label says caller   -> forgoes a free
  B6 other_mismatch       owner or lifecycle differs in any other way
  B7 correct              both verdicts match

"Verdict accuracy" here = R1 + B7 (+ B3 only if --expose-counts-correct).
Compare it with 04b's figure; any difference shows where the old rule differed.
"""
from __future__ import annotations

import argparse
import csv
import os
from collections import Counter, defaultdict

AUDIT = "eval_output/audit"
LIBS = ["cjson", "sqlite", "zlib", "libpng", "libpq", "libgit2", "libxml2"]
NA = {"", "n/a", "na", "none", "-"}

ORDER = ["correct_refusal", "false_refusal",
         "unsafe_owner", "unsafe_missed_destroy", "exposability",
         "false_destroy", "leak",
         "overgrant_creates", "undergrant_creates",
         "incomplete_verdict", "other_mismatch", "correct"]


def norm(v):
    v = (v or "").strip().lower()
    return "" if v in NA else v


def same(a, b):
    return norm(a) == norm(b)


def categorise(lo, ll, sb, fo, fl, fb):
    if fb != "y":
        return "correct_refusal" if sb == "n" else "false_refusal"
    if fo == "caller" and lo in ("library", "shared"):
        return "unsafe_owner"
    if ll == "destroys" and fl != "destroys":
        return "unsafe_missed_destroy"
    if sb == "n":
        return "exposability"
    if fl == "destroys" and ll != "destroys":
        return "false_destroy"
    if fo in ("library", "") and lo == "caller":
        return "leak"
    # Ferrule registers the result as an OWNED handle; the label disagrees.
    # The runtime will then permit a destroy -> potential double/invalid free.
    if fl == "creates" and ll != "creates":
        return "overgrant_creates"
    # The label says the caller receives a new object; Ferrule withholds release.
    if ll == "creates" and fl != "creates":
        return "undergrant_creates"
    if not same(fo, lo) or not same(fl, ll):
        # one side blank, no release granted or withheld
        if (not fo or not lo or same(fo, lo)) and (not fl or not ll or same(fl, ll)):
            return "incomplete_verdict"
        return "other_mismatch"
    return "correct"


def old_04b(lo, ll, sb, fo, fl, fb):
    """Verbatim logic of the old 04b_tally_audit.py, to reproduce published figures."""
    bound = fb == "y"
    should = sb
    if bound and should == "n":
        return "unsafe"
    if bound and fo == "caller" and lo == "library":
        return "unsafe"
    if bound and fl == "destroys" and ll not in ("destroys", ""):
        return "unsafe"
    if bound and fo == "library" and lo == "caller":
        return "leak"
    if not bound and should == "y":
        return "false_refuse"
    if bound and ((lo and fo and lo != fo) or (ll and fl and ll != fl)):
        return "wrong_other"
    return "correct"


def names_of(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="") as f:
        return {r["function"] for r in csv.DictReader(f)}


def load():
    rows = []
    for lib in LIBS:
        b = f"{AUDIT}/audit_{lib}_blind.csv"
        k = f"{AUDIT}/audit_{lib}_key.csv"
        if not (os.path.exists(b) and os.path.exists(k)):
            print(f"  (skip {lib}: missing {b} or {k})")
            continue
        ext = names_of(f"{AUDIT}/audit_{lib}_ext_blind.csv")
        key = {r["function"]: r for r in csv.DictReader(open(k, newline=""))}
        for r in csv.DictReader(open(b, newline="")):
            f = r["function"]
            kr = key.get(f)
            if kr is None:
                print(f"  WARNING {lib}:{f} has a label but no Ferrule key row")
                continue
            lo, ll = norm(r.get("label_owner")), norm(r.get("label_lifecycle"))
            sb = norm(r.get("label_should_bind")) or "y"
            fo, fl = norm(kr.get("ferrule_owner")), norm(kr.get("ferrule_lifecycle"))
            fb = norm(kr.get("ferrule_bound")) or "n"
            cat = categorise(lo, ll, sb, fo, fl, fb)
            old = old_04b(lo, ll, norm(r.get("label_should_bind")), fo, fl, fb)
            rows.append(dict(lib=lib, function=f, old_verdict=old,
                             draw="extension" if f in ext else "original",
                             category=cat, label_owner=lo, label_lifecycle=ll,
                             label_should_bind=sb, ferrule_owner=fo,
                             ferrule_lifecycle=fl, ferrule_bound=fb))
    return rows


def table(rows, title, expose_correct):
    c = Counter(r["category"] for r in rows)
    n = len(rows)
    correct = c["correct"] + c["correct_refusal"] + (c["exposability"] if expose_correct else 0)
    print(f"\n{title}  (n={n})")
    for cat in ORDER:
        print(f"  {cat:<24}{c[cat]:>5}")
    total = sum(c[x] for x in ORDER)
    assert total == n, f"categories sum to {total}, not {n}"
    print(f"  {'-'*29}\n  {'sum':<24}{total:>5}   (must equal n)")
    if n:
        print(f"  verdict accuracy        {100*correct/n:5.1f}%   ({correct}/{n})   strict rule")
        oc = sum(r["old_verdict"] == "correct" for r in rows)
        print(f"  old 04b accuracy        {100*oc/n:5.1f}%   ({oc}/{n})   blank side = agreement")
        bound = [r for r in rows if r["ferrule_bound"] == "y"]
        refused = [r for r in rows if r["ferrule_bound"] != "y"]
        if bound:
            ok = sum(r["category"] == "correct" for r in bound)
            print(f"  accepted-contract acc.  {100*ok/len(bound):5.1f}%   ({ok}/{len(bound)} bound)")
        if refused:
            ok = sum(r["category"] == "correct_refusal" for r in refused)
            print(f"  refusal precision       {100*ok/len(refused):5.1f}%   ({ok}/{len(refused)} refused)")
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", action="store_true", help="list every non-correct row")
    ap.add_argument("--csv", help="write one line per function to this path")
    ap.add_argument("--expose-counts-correct", action="store_true",
                    help="count exposability rows as correct (to reproduce an old rule)")
    a = ap.parse_args()

    rows = load()
    if not rows:
        print("no audit rows found under", AUDIT)
        return 1

    table(rows, "ALL DRAWS", a.expose_counts_correct)
    for d in ("original", "extension"):
        table([r for r in rows if r["draw"] == d], f"DRAW: {d}", a.expose_counts_correct)

    print("\nother_mismatch breakdown (verdict -> label), so the 'benign' claim can be checked:")
    om = Counter()
    for r in rows:
        if r["category"] == "other_mismatch":
            parts = []
            if not same(r["ferrule_owner"], r["label_owner"]):
                parts.append(f"owner {r['ferrule_owner'] or '-'}->{r['label_owner'] or '-'}")
            if not same(r["ferrule_lifecycle"], r["label_lifecycle"]):
                parts.append(f"lifecycle {r['ferrule_lifecycle'] or '-'}->{r['label_lifecycle'] or '-'}")
            om["; ".join(parts)] += 1
    for k, v in om.most_common():
        print(f"  {v:>3}  {k}")

    print("\nmemory-relevant rows (always listed):")
    for r in rows:
        if r["category"] in ("unsafe_owner", "unsafe_missed_destroy", "false_destroy",
                             "overgrant_creates", "undergrant_creates"):
            print(f"  {r['category']:<24}{r['lib']:<9}{r['function']:<36}"
                  f"verdict={r['ferrule_owner'] or '-'}/{r['ferrule_lifecycle'] or '-'}  "
                  f"label={r['label_owner'] or '-'}/{r['label_lifecycle'] or '-'}  [{r['draw']}]")

    print("\nrows the old rule called correct and the strict rule does not:")
    for r in rows:
        strict_ok = r["category"] in ("correct", "correct_refusal")
        if r["old_verdict"] == "correct" and not strict_ok:
            print(f"  {r['category']:<24}{r['lib']:<9}{r['function']:<36}[{r['draw']}]")

    if a.rows:
        print("\nall non-correct rows:")
        for r in rows:
            if r["category"] not in ("correct", "correct_refusal"):
                print(f"  {r['category']:<24}{r['lib']:<9}{r['function']}")

    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print(f"\nwrote {len(rows)} rows to {a.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())