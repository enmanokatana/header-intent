"""
Confidence-threshold sensitivity sweep.  (fix F15)

policy.sweep_thresholds() already exists and already separates the refusals the
threshold controls (rule 3, low-confidence unverified) from the hard safety rules
that fire at every threshold. That separation is exactly what makes the curve
interpretable -- and it is not in the paper. This runs it over every stored spec and
emits both a table and a pgfplots figure.

The result is useful whichever way it goes:
  * curve moves  -> 0.5 is a tuned hyperparameter; justify it from the knee.
  * curve flat   -> the threshold contributes nothing to the present results, which
                    is worth one honest sentence and disarms the "arbitrary magic
                    number" objection permanently.

Usage
-----
    python3 07_threshold_sweep.py --repo /path/to/header-intent \\
        eval_results/*/spec.yaml --latex sweep_table.tex --figure sweep_figure.tex
"""
from __future__ import annotations

import argparse
import sys

THRESHOLDS = [0.3, 0.4, 0.5, 0.6, 0.7]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--latex")
    ap.add_argument("--figure")
    args = ap.parse_args()

    sys.path.insert(0, args.repo)
    from src.spec.io import load_yaml
    from src.core.policy import sweep_thresholds

    series = {}
    for path in args.specs:
        spec = load_yaml(path)
        rows = sweep_thresholds(spec, THRESHOLDS)
        series[spec.library] = rows
        print(f"\n{spec.library}  ({len(spec.functions)} functions)")
        print(f"  {'thr':>5} {'buildable':>10} {'refused':>8} {'by rule 3':>10} "
              f"{'hard rules':>11}")
        for t, buildable, refused, lowconf in rows:
            print(f"  {t:>5.1f} {buildable:>10} {refused:>8} {lowconf:>10} "
                  f"{refused - lowconf:>11}")

    moved = {lib: rows[0][1] - rows[-1][1] for lib, rows in series.items()}
    print("\ncoverage delta 0.3 -> 0.7 (functions lost as the gate tightens):")
    for lib, d in moved.items():
        print(f"  {lib:10} {d:>4}")
    if all(d == 0 for d in moved.values()):
        print("\nFLAT. Every refusal is a hard-rule refusal; the threshold controls")
        print("nothing in this evaluation. Paper sentence:")
        print('  "Coverage is insensitive to the threshold across 0.3-0.7 because')
        print('   refusals are dominated by the hard safety rules; we retain the')
        print('   confidence score for the evidence trail rather than for gating."')

    if args.latex:
        with open(args.latex, "w") as f:
            for lib, rows in series.items():
                for t, buildable, refused, lowconf in rows:
                    f.write(f"{lib} & {t:.1f} & {buildable} & {refused} & {lowconf} \\\\\n")
        print(f"\nwrote {args.latex}")

    if args.figure:
        with open(args.figure, "w") as f:
            f.write("% requires \\usepackage{pgfplots}\n")
            f.write("\\begin{figure}[t]\\centering\n\\begin{tikzpicture}\n")
            f.write("\\begin{axis}[width=\\columnwidth,height=5cm,\n"
                    "  xlabel={confidence threshold}, ylabel={functions bound},\n"
                    "  legend style={font=\\scriptsize,at={(0.5,-0.28)},anchor=north,legend columns=3},\n"
                    "  grid=both, tick align=outside]\n")
            for lib, rows in series.items():
                coords = " ".join(f"({t:.1f},{b})" for t, b, _, _ in rows)
                f.write(f"\\addplot coordinates {{{coords}}};\n")
                f.write(f"\\addlegendentry{{{lib}}}\n")
            f.write("\\end{axis}\n\\end{tikzpicture}\n")
            f.write("\\caption{Confidence-threshold sensitivity. Only functions refused by "
                    "the low-confidence rule move with the threshold; refusals from the hard "
                    "safety rules (opaque parameter, unmanaged raw \\texttt{void*}) are "
                    "threshold-independent.}\n\\label{fig:sweep}\n\\end{figure}\n")
        print(f"wrote {args.figure}")


if __name__ == "__main__":
    main()
