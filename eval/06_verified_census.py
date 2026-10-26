"""
Verification census.  (fix F14)

The paper lists behavioral verification as contribution #1 and never says how often
it fires. The guards in verify/probes.py are severe -- the ENTIRE signature must be
scalar, and there must be a by-ref out/inout parameter -- so on a handle-oriented API
the eligible set may be empty. A reviewer who works that out unprompted will not be
kind about it; reporting the number yourself costs nothing and buys credibility.

Counts, per library:

    exported           functions in the spec
    eligible           would pass verify_out_params' guards
    probed             eligible AND had at least one candidate out-param
    verified_facts     params with intent.verified == True
    halved             params whose confidence was halved by a failed probe
    decisions_changed  functions whose exposability differs with vs without the
                       verified flag (i.e. where verification actually mattered)

Usage
-----
    python3 06_verified_census.py --repo /path/to/header-intent \\
        eval_results/*/spec.yaml --latex verification_table.tex
"""
from __future__ import annotations

import argparse
import copy
import sys


def census(repo, spec_path):
    sys.path.insert(0, repo)
    from src.spec.io import load_yaml
    from src.spec.vocab import Role, Intent
    from src.core.policy import is_exposable

    spec = load_yaml(spec_path)
    stats = dict(library=spec.library, exported=len(spec.functions), eligible=0,
                 probed=0, verified_facts=0, halved=0, decisions_changed=0)

    for fn in spec.functions.values():
        # mirrors verify_out_params' guard exactly
        eligible = not any(p.role in (Role.STRING, Role.OPAQUE, Role.HANDLE, Role.ARRAY)
                           for p in fn.params)
        if eligible:
            stats["eligible"] += 1
            candidates = [p for p in fn.params
                          if p.by_ref and p.intent.value in (Intent.OUT, Intent.INOUT)]
            if candidates:
                stats["probed"] += 1

        v = sum(1 for p in fn.params if p.intent.verified)
        stats["verified_facts"] += v
        # a halved fact is one carrying the probe source but not the verified flag
        stats["halved"] += sum(1 for p in fn.params
                               if not p.intent.verified
                               and "behavioral_probe" in p.intent.sources)
        if v:
            shadow = copy.deepcopy(fn)
            for p in shadow.params:
                p.intent.verified = False
            if is_exposable(fn) != is_exposable(shadow):
                stats["decisions_changed"] += 1
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--latex")
    args = ap.parse_args()

    rows = [census(args.repo, s) for s in args.specs]
    hdr = ("library", "exported", "eligible", "probed", "verified_facts", "halved",
           "decisions_changed")
    print("  ".join(h.rjust(16) if h != "library" else h.ljust(10) for h in hdr))
    print("-" * 100)
    for r in rows:
        print("  ".join([str(r["library"]).ljust(10)]
                        + [str(r[h]).rjust(16) for h in hdr[1:]]))

    tot = sum(r["verified_facts"] for r in rows)
    print()
    if tot == 0:
        print("verified_facts == 0 across every library.")
        print("  -> Say so in the paper, drop 'Verified' from the title (fix F1),")
        print("     and reframe the probe as a guard on a specific parameter shape")
        print("     rather than as a pipeline stage. A reported zero is a limitation;")
        print("     an unreported zero is a credibility problem.")
    else:
        print(f"{tot} verified facts across {len(rows)} libraries; "
              f"{sum(r['decisions_changed'] for r in rows)} exposability decisions "
              f"actually depended on verification.")

    if args.latex:
        with open(args.latex, "w") as f:
            for r in rows:
                f.write(f"{r['library']} & {r['eligible']} & {r['probed']} & "
                        f"{r['verified_facts']} & {r['decisions_changed']} \\\\\n")
        print(f"wrote {args.latex}")


if __name__ == "__main__":
    main()
