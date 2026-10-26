"""
Stratified, BLIND ground-truth sampler.  (fix F11/F12)

Supersedes 03_sample_audit.py, which sampled only functions that survived into the
spec and showed the labeller Ferrule's verdict. Both are biases the paper cannot
afford:

  * sampling only survivors makes FALSE REFUSALS unmeasurable, and refusals are
    half of what the fail-safe claim rests on;
  * showing the verdict while labelling turns the exercise into agreement-seeking.

This emits two files per library:

    audit_<lib>_blind.csv   no verdict column -- this is what a labeller fills in
    audit_<lib>_key.csv     Ferrule's verdicts -- scored against the labels later

Strata (sampled independently so the rare, dangerous cases are represented):

    handle_return   function returns a pointer to a handle type   <- ownership risk
    lifecycle       lifecycle-relevant by name (_new/_free/...)   <- release risk
    refused         Ferrule declined to bind it                   <- false-refuse rate
    other           everything else                               <- base rate

Usage
-----
    python3 03b_sample_audit.py --repo /path/to/header-intent \\
        --spec eval_results/libpq/spec.yaml --so /usr/lib/.../libpq.so \\
        --lib libpq --per-stratum 5 --seed 20260914 --out .

    # second annotator sheet for the agreement measurement (subset, same rows)
    python3 03b_sample_audit.py ... --second-annotator 30

Label the blind sheet with these columns:

    label_owner       caller | library | shared | na
    label_lifecycle   creates | uses | destroys | na
    label_should_bind y | n          (is it SAFE to expose this function at all?)
    label_source      doc | source | both     (where the label came from)
    notes

`label_should_bind = n` means a correct binding is impossible without a contract the
tool cannot have (e.g. a callback whose lifetime is undocumented), so a refusal is
the right answer and must NOT be counted as a false refusal.
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import re
import sys

CREATE = re.compile(r"_(new|create|alloc|open|dup|clone|init)\b|(new|create|alloc|dup|init)$", re.I)
DESTROY = re.compile(r"_(free|dispose|delete|close|destroy|release|unref|finish|clear|end)\b", re.I)

BLIND_COLS = ["function", "signature", "stratum",
              "label_owner", "label_lifecycle", "label_should_bind",
              "label_source", "notes"]
KEY_COLS = ["function", "stratum", "ferrule_owner", "ferrule_lifecycle",
            "ferrule_bound", "refusal_reason"]


def load(repo, spec_path, so_path):
    """Return {name: (fnspec, bound: bool, reason: str)} using the real policy."""
    sys.path.insert(0, repo)
    import ctypes
    from src.spec.io import load_yaml
    from src.core.invoker import build_capabilities
    from src.core.handles import HandleTable

    spec = load_yaml(spec_path)
    lib = ctypes.CDLL(so_path)
    caps, refused = build_capabilities(lib, spec, HandleTable())
    bound = {c.name for c in caps}
    reasons = {}
    for r in refused:
        # build_capabilities returns either (name, reason) pairs or reason strings
        if isinstance(r, (tuple, list)) and len(r) == 2:
            reasons[r[0]] = r[1]
        else:
            text = str(r)
            reasons[text.split(":")[0].strip()] = text
    out = {}
    for name, fn in spec.functions.items():
        out[name] = (fn, name in bound, reasons.get(name, "" if name in bound else "refused"))
    return out


def signature_of(fn) -> str:
    ps = ", ".join(f"{p.ctype}{'*' if getattr(p, 'by_ref', False) else ''} {p.name}"
                   for p in fn.params)
    return f"{fn.restype or 'void'} {fn.name}({ps})"


def stratum_of(name, fn, bound) -> str:
    if not bound:
        return "refused"
    if fn.lifecycle in ("creates", "borrows") or (fn.restype == "c_void_p" and fn.handle_type):
        return "handle_return"
    if CREATE.search(name) or DESTROY.search(name) or fn.lifecycle:
        return "lifecycle"
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="path to the header-intent checkout")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--so", required=True)
    ap.add_argument("--lib", required=True)
    ap.add_argument("--per-stratum", type=int, default=5)
    ap.add_argument("--seed", type=int, default=20260914)
    ap.add_argument("--out", default=".")
    ap.add_argument("--second-annotator", type=int, default=0,
                    help="also emit a subset sheet of N rows for a second labeller")
    args = ap.parse_args()

    table = load(args.repo, args.spec, args.so)
    buckets: dict[str, list] = {}
    for name, (fn, bound, reason) in table.items():
        buckets.setdefault(stratum_of(name, fn, bound), []).append((name, fn, bound, reason))

    random.seed(args.seed)
    sample = []
    for stratum in ("handle_return", "lifecycle", "refused", "other"):
        rows = buckets.get(stratum, [])
        take = random.sample(rows, min(args.per_stratum, len(rows)))
        sample.extend((stratum, *r) for r in take)
    sample.sort(key=lambda r: r[1])

    os.makedirs(args.out, exist_ok=True)
    blind_path = os.path.join(args.out, f"audit_{args.lib}_blind.csv")
    key_path = os.path.join(args.out, f"audit_{args.lib}_key.csv")

    with open(blind_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(BLIND_COLS)
        for stratum, name, fn, bound, reason in sample:
            w.writerow([name, signature_of(fn), stratum, "", "", "", "", ""])

    with open(key_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(KEY_COLS)
        for stratum, name, fn, bound, reason in sample:
            w.writerow([name, stratum, fn.owner or "", fn.lifecycle or "",
                        "y" if bound else "n", reason])

    if args.second_annotator:
        sub = random.sample(sample, min(args.second_annotator, len(sample)))
        sub.sort(key=lambda r: r[1])
        p2 = os.path.join(args.out, f"audit_{args.lib}_blind_annotator2.csv")
        with open(p2, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(BLIND_COLS)
            for stratum, name, fn, bound, reason in sub:
                w.writerow([name, signature_of(fn), stratum, "", "", "", "", ""])
        print(f"wrote {p2} ({len(sub)} rows)", file=sys.stderr)

    counts = {s: len(buckets.get(s, [])) for s in ("handle_return", "lifecycle", "refused", "other")}
    print(f"wrote {blind_path} and {key_path}: {len(sample)} sampled "
          f"from {sum(counts.values())} exported (population per stratum: {counts}, "
          f"seed={args.seed})", file=sys.stderr)
    print("NOTE: label the *_blind.csv WITHOUT opening the *_key.csv.", file=sys.stderr)


if __name__ == "__main__":
    main()
