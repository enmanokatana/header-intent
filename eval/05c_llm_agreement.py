#!/usr/bin/env python3
"""
LLM baseline: abstention and run-to-run agreement.

    python3 eval/05c_llm_agreement.py
    python3 eval/05c_llm_agreement.py --runs 1 2 --latex snapshots/table_llm.tex

Reads snapshots/llm/raw_<lib>_llm<N>.json (the model's actual answers, before
the CSV flattens "unknown") and reports the two properties II-E asserts:

  ABSTENTION        how often it answered "unknown" when that was offered and
                    described as preferable to guessing
  AGREEMENT         how often two runs of an identical prompt agree, per field,
                    with Cohen's kappa alongside raw agreement -- kappa matters
                    because these fields are skewed, and a model that always
                    says "library" would score high raw agreement while
                    carrying no information

Accuracy against the labels is NOT computed here: 04b_tally_audit.py already
does that, against the same labels and the same definitions of unsafe and
leak, which is what makes the comparison with Ferrule meaningful.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
from collections import Counter

RAW = "snapshots/llm"
LIBS = ["cjson", "sqlite", "zlib", "libpng", "libpq", "libgit2"]
FIELDS = ["owner", "lifecycle", "safe_to_expose"]


def kappa(pairs):
    """Cohen's kappa over (a, b) label pairs."""
    n = len(pairs)
    if n == 0:
        return None
    obs = sum(1 for a, b in pairs if a == b) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    exp = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    if exp >= 1.0:
        return 1.0 if obs >= 1.0 else 0.0
    return (obs - exp) / (1 - exp)


def load(lib, run):
    p = f"{RAW}/raw_{lib}_llm{run}.json"
    return json.load(open(p)) if os.path.exists(p) else None


def main():
    global RAW
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs=2, type=int, default=[1, 2])
    ap.add_argument("--dir", default=RAW,
                    help="vendor directory, e.g. snapshots/llm_gpt")
    ap.add_argument("--latex")
    args = ap.parse_args()
    r1, r2 = args.runs
    RAW = args.dir
    prov = os.path.join(RAW, "provenance.json")
    if os.path.exists(prov):
        import json as _json
        p = _json.load(open(prov))
        print(f"\n{p.get('provider')} / {p.get('model')}"
              + ("  [no rubric]" if p.get("no_rubric") else "")
              + f"   run {p.get('when')}")

    per_lib, all_pairs = [], {f: [] for f in FIELDS}
    abstain = {f: Counter() for f in FIELDS}
    flips = []
    errors = 0

    for lib in LIBS:
        a, b = load(lib, r1), load(lib, r2)
        if a is None:
            continue
        def failed(d, n):
            return str((d.get(n) or {}).get("reason", "")).startswith("error:")

        for name, ans in a.items():
            if failed(a, name) or (b is not None and failed(b, name)):
                errors += 1
                continue
            for f in FIELDS:
                abstain[f][ans.get(f, "unknown")] += 1
        if b is None:
            continue
        same = {f: 0 for f in FIELDS}
        # an entry that failed in either run is excluded from both measures:
        # a transport failure is not an abstention and not a disagreement
        shared = [n for n in a if n in b
                  and not failed(a, n) and not failed(b, n)]
        for n in shared:
            for f in FIELDS:
                x, y = a[n].get(f, "unknown"), b[n].get(f, "unknown")
                all_pairs[f].append((x, y))
                if x == y:
                    same[f] += 1
                elif f == "owner" and {x, y} == {"caller", "library"}:
                    flips.append((lib, n, x, y))
        per_lib.append((lib, len(shared), same))

    n_total = sum(r[1] for r in per_lib)
    print(f"\nLLM baseline -- runs {r1} and {r2}, {n_total} functions\n")

    print("ABSTENTION  (how often it answered \"unknown\")")
    for f in FIELDS:
        c = abstain[f]
        tot = sum(c.values())
        unk = c.get("unknown", 0)
        dist = "  ".join(f"{k}={v}" for k, v in c.most_common())
        print(f"  {f:<16} unknown {unk:>3}/{tot:<4} "
              f"({100*unk/tot if tot else 0:>4.0f}%)   {dist}")

    print("\nRUN-TO-RUN AGREEMENT")
    print(f"  {'field':<16}{'agree':>8}{'raw':>8}{'kappa':>8}")
    for f in FIELDS:
        pairs = all_pairs[f]
        if not pairs:
            continue
        agree = sum(1 for x, y in pairs if x == y)
        k = kappa(pairs)
        print(f"  {f:<16}{agree:>4}/{len(pairs):<3}{100*agree/len(pairs):>7.0f}%"
              f"{('  n/a' if k is None else f'{k:>8.2f}')}")

    if per_lib:
        print("\n  per library (agreements per field)")
        for lib, n, same in per_lib:
            cells = "  ".join(f"{f[:4]}={same[f]}/{n}" for f in FIELDS)
            print(f"    {lib:<9} {cells}")

    if flips:
        print(f"\nOWNERSHIP FLIPS BETWEEN RUNS  ({len(flips)})")
        print("  caller<->library on an identical prompt: one of the two runs "
              "would\n  have produced a double free or a leak.")
        for lib, n, x, y in flips[:15]:
            print(f"    {lib:<9} {n:<38} run{r1}={x:<8} run{r2}={y}")
        if len(flips) > 15:
            print(f"    ... and {len(flips) - 15} more")
    else:
        print("\nOWNERSHIP FLIPS BETWEEN RUNS: none")

    if errors:
        print(f"\n  ! {errors} functions excluded: the call failed in at least "
              f"one run\n    (retry them with eval/05e_retry_errors.py; "
              f"persistent failures are a\n    provider asymmetry worth "
              f"reporting, not an abstention)")

    if args.latex:
        with open(args.latex, "w") as fh:
            fh.write("""\\begin{table}[!t]
\\caption{LLM baseline on the same %d labelled functions. ``Unknown'' is the
abstention rate when that answer was offered and described as preferable to
guessing; ``agree'' is the fraction of identical prompts answered the same way
across two runs.}
\\label{tab:llm}
\\centering\\footnotesize
\\begin{tabular}{lrrr}
\\toprule
\\textbf{Field} & \\textbf{Unknown} & \\textbf{Agree} & \\textbf{$\\kappa$} \\\\
\\midrule
""" % n_total)
            for f in FIELDS:
                pairs = all_pairs[f]
                if not pairs:
                    continue
                tot = sum(abstain[f].values())
                unk = abstain[f].get("unknown", 0)
                agree = sum(1 for x, y in pairs if x == y)
                k = kappa(pairs)
                fh.write(f"\\texttt{{{f.replace('_', chr(92)*1 + '_')}}} & "
                         f"{100*unk/tot if tot else 0:.0f}\\% & "
                         f"{100*agree/len(pairs):.0f}\\% & "
                         f"{'--' if k is None else f'{k:.2f}'} \\\\\n")
            fh.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")
        print(f"\nwrote {args.latex}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
