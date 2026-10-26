#!/usr/bin/env python3
"""
Build the two LLM tables from the artifacts. Nothing transcribed by hand.

    python3 eval/06_llm_tables.py

Accuracy comes from 04b_tally_audit.py run as a subprocess, so the numbers are
produced by the same scorer that scores Ferrule -- not by a reimplementation
that could drift from it. Abstention and agreement come from the raw JSON.

Writes:
    snapshots/table_llm.tex          per condition: accuracy, safety, abstention, kappa
    snapshots/table_llm_overlap.tex  functions both models expose unaided
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter

AUDIT = "eval_output/audit"
LIBS = ["cjson", "sqlite", "zlib", "libpng", "libpq", "libgit2"]
FIELDS = ["owner", "lifecycle", "safe_to_expose"]

CONDITIONS = [
    ("Claude, criteria given", "snapshots/llm"),
    ("GPT, criteria given", "snapshots/llm_gpt"),
    ("Claude, criteria withheld", "snapshots/llm_claude-norubric"),
    ("GPT, criteria withheld", "snapshots/llm_gpt-norubric"),
]


def kappa(pairs):
    n = len(pairs)
    if not n:
        return None
    obs = sum(1 for a, b in pairs if a == b) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    exp = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    return 1.0 if exp >= 1.0 else (obs - exp) / (1 - exp)


def score(d):
    """Run the real scorer; return (accuracy, unsafe, leak, false_ref, unsafe_fns)."""
    pairs = []
    for lib in LIBS:
        k = f"{d}/audit_{lib}_llm1.csv"
        if os.path.exists(k):
            pairs += ["--pairs", f"{AUDIT}/audit_{lib}_blind.csv:{k}"]
    if not pairs:
        return None
    out = subprocess.run([sys.executable, "eval/04b_tally_audit.py"] + pairs,
                         capture_output=True, text=True).stdout
    m = re.search(r"accuracy\s+([\d.]+)%\s+unsafe\s+([\d.]+)%\s+leak\s+([\d.]+)%"
                  r"\s+false-refuse\s+([\d.]+)%", out)
    row = re.search(r"OVERALL\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", out)
    fns = re.findall(r"\[unsafe\]\s+(\w+):", out)
    if not (m and row):
        return None
    return dict(acc=float(m.group(1)), n=int(row.group(1)),
                correct=int(row.group(2)), unsafe=int(row.group(3)),
                leak=int(row.group(4)), false_ref=int(row.group(5)),
                unsafe_fns=fns)


def raw_stats(d):
    abst = {f: Counter() for f in FIELDS}
    pair = {f: [] for f in FIELDS}
    for lib in LIBS:
        p1, p2 = f"{d}/raw_{lib}_llm1.json", f"{d}/raw_{lib}_llm2.json"
        if not os.path.exists(p1):
            continue
        a = json.load(open(p1))
        b = json.load(open(p2)) if os.path.exists(p2) else None

        def bad(x, n):
            return str((x.get(n) or {}).get("reason", "")).startswith("error:")
        for n, ans in a.items():
            if bad(a, n) or (b and bad(b, n)):
                continue
            for f in FIELDS:
                abst[f][ans.get(f, "unknown")] += 1
            if b and n in b:
                pair[f].append((ans.get(f, "unknown"), b[n].get(f, "unknown")))
        if b:
            for n in a:
                if bad(a, n) or bad(b, n) or n not in b:
                    continue
                for f in FIELDS:
                    pair[f].append((a[n].get(f, "unknown"), b[n].get(f, "unknown")))
    return abst, pair


def ferrule_refusals():
    out = {}
    import csv
    for lib in LIBS:
        p = f"{AUDIT}/audit_{lib}_key.csv"
        if os.path.exists(p):
            for r in csv.DictReader(open(p)):
                out[r["function"]] = (r["ferrule_bound"], r["refusal_reason"])
    return out


def main():
    rows = []
    for label, d in CONDITIONS:
        s = score(d)
        if s is None:
            print(f"  ! {label}: no data in {d}")
            continue
        abst, pair = raw_stats(d)
        ks = {}
        for f in FIELDS:
            seen, uniq = set(), []
            for t in pair[f]:
                uniq.append(t)
            ks[f] = kappa(uniq) if uniq else None
        un = {f: (abst[f].get("unknown", 0), sum(abst[f].values())) for f in FIELDS}
        rows.append((label, s, un, ks))

    print(f"\n{'condition':<28}{'acc':>7}{'unsafe':>8}{'leak':>6}{'f-ref':>7}"
          f"{'abstain':>22}{'kappa':>20}")
    for label, s, un, ks in rows:
        a = "/".join(f"{100*v/t if t else 0:.0f}%" for v, t in
                     (un[f] for f in FIELDS))
        k = "/".join("--" if ks[f] is None else f"{ks[f]:.2f}" for f in FIELDS)
        print(f"{label:<28}{s['acc']:>6.1f}%{s['unsafe']:>8}{s['leak']:>6}"
              f"{s['false_ref']:>7}{a:>22}{k:>20}")

    # overlap: functions BOTH models expose when the criteria are withheld
    nr = {label: set(s["unsafe_fns"]) for label, s, _, _ in rows
          if "withheld" in label}
    if len(nr) == 2:
        a, b = nr.values()
        both, either = sorted(a & b), sorted(a | b)
        fr = ferrule_refusals()
        print(f"\nunsafe with criteria withheld: "
              f"{len(both)} shared, {len(either)} in either")
        print(f"  {'function':<36}{'ferrule':<9}reason")
        for fn in either:
            bound, reason = fr.get(fn, ("?", ""))
            mark = "both" if fn in both else "one"
            print(f"  {fn:<36}{bound:<9}{reason[:44]}   [{mark}]")
        refused = sum(1 for fn in both if fr.get(fn, ("?",))[0] == "n")
        print(f"\n  of the {len(both)} both models expose, "
              f"Ferrule refuses {refused}")

        with open("snapshots/table_llm_overlap.tex", "w") as fh:
            fh.write("""\\begin{table}[!t]
\\caption{Functions both models judge safe to expose when the exposability
criteria are withheld from the prompt, with the reason Ferrule's structural
policy refuses each.}
\\label{tab:llm-overlap}
\\centering\\footnotesize
\\begin{tabular}{llp{3.4cm}}
\\toprule
\\textbf{Function} & \\textbf{Ferrule} & \\textbf{Reason} \\\\
\\midrule
""")
            for fn in both:
                bound, reason = fr.get(fn, ("?", ""))
                r = reason.split(":", 1)[-1].strip()[:60] or "---"
                fh.write(f"\\texttt{{{fn.replace('_', chr(92) + '_')}}} & "
                         f"{'refused' if bound == 'n' else 'bound'} & "
                         f"{r.replace('_', chr(92) + '_')} \\\\\n")
            fh.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")
        print("  wrote snapshots/table_llm_overlap.tex")

    with open("snapshots/table_llm.tex", "w") as fh:
        fh.write("""\\begin{table}[!t]
\\caption{Learned contracts on the same 99 labelled functions, scored by the
same program as Table~\\ref{tab:accuracy}. ``Criteria given'' states in the
prompt which parameter shapes make a function unbindable; ``criteria withheld''
asks the model to decide unaided. Abstention is the rate of \\texttt{unknown}
when it was offered and described as preferable to guessing. $\\kappa$ is
agreement between two runs of an identical prompt.}
\\label{tab:llm}
\\centering\\footnotesize
\\begin{tabular}{lrrrrl}
\\toprule
\\textbf{Condition} & \\textbf{Acc.} & \\textbf{Unsafe} & \\textbf{Leak} &
\\textbf{False ref.} & \\textbf{Abstain / $\\kappa$} \\\\
\\midrule
""")
        for label, s, un, ks in rows:
            a = "/".join(f"{100*v/t if t else 0:.0f}" for v, t in
                         (un[f] for f in FIELDS))
            k = "/".join("--" if ks[f] is None else f"{ks[f]:.2f}" for f in FIELDS)
            fh.write(f"{label} & {s['acc']:.1f}\\% & {s['unsafe']} & {s['leak']} "
                     f"& {s['false_ref']} & {a}\\% \\quad {k} \\\\\n")
        fh.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")
    print("wrote snapshots/table_llm.tex")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
