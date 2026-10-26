#!/usr/bin/env python3
"""
Ablation: what each layer buys, and what the prior approach's failure mode costs.

    python3 eval/07_ablation.py

Four configurations over the same 99 labelled functions, scored by the same
program that scores Ferrule and the language models:

  A  all-borrow       binds everything, owns nothing. The floor: it cannot
                      produce a double free because it never permits a free,
                      and it is useless for the same reason.
  B  structural only  the type-directed filter alone -- refuse a function
                      pointer parameter, a non-const char*, a raw void*
                      return, or a variadic signature -- with no ownership
                      notion. This is T1 plus a safety filter.
  C  Ravitch-style    the idiom analyses without the owned-versus-borrowed
                      distinction and without abstention. Ravitch et al.
                      recover which functions acquire and release a resource
                      but not whether a returned pointer transfers ownership,
                      and their generator emits a binding for every function
                      it processes.
  D  Ferrule          unchanged.

A and B are built from the HEADER ALONE, via libclang, so they see what a
type-directed generator sees. Building them from Ferrule's spec would give
them L2's resolved pointees and propagated handle types for free and make the
ablation flatter than the truth.

C is built by deleting the ownership distinction from Ferrule's own frozen
spec: every lifecycle verdict that hands back a handle becomes owner=caller.
This is an OPERATIONALISATION of the approach as described, not their
implementation, which we could not run. It errs in their favour on every other
axis, since it gives them our idiom recovery unchanged.

The capability column is the point of the all-borrow row: a configuration that
frees nothing scores perfectly on every safety measure in this paper. It counts
functions the configuration says the caller may free AND the label agrees.
"""
from __future__ import annotations

import csv
import importlib.util
import os
import re
import subprocess
import sys

from clang import cindex

AUDIT = "eval_output/audit"
OUT = "snapshots/ablation"
LIBS = ["cjson", "sqlite", "zlib", "libpng", "libpq", "libgit2"]
COLS = ["function", "stratum", "ferrule_owner", "ferrule_lifecycle",
        "ferrule_bound", "refusal_reason"]


def load_mod(name):
    p = os.path.join(os.path.dirname(__file__), name)
    spec = importlib.util.spec_from_file_location(name.replace(".", "_"), p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------------------------------------------------------------- A and B
def header_shapes(header, args, names):
    """{name: {"variadic":.., "callback":.., "wbuf":.., "voidp":..}} from the
    header alone -- no source analysis, no spec."""
    k = cindex.TypeKind
    out = {}
    tu = cindex.Index.create().parse(header, args=args)
    for c in tu.cursor.walk_preorder():
        if c.kind != cindex.CursorKind.FUNCTION_DECL or c.spelling not in names:
            continue
        if c.spelling in out:
            continue
        d = {"variadic": False, "callback": False, "wbuf": False, "voidp": False}
        try:
            d["variadic"] = c.type.is_function_variadic()
        except Exception:
            pass
        rt = c.result_type.get_canonical()
        if rt.kind == k.POINTER and rt.get_pointee().get_canonical().kind == k.VOID:
            d["voidp"] = True
        for a in c.get_arguments():
            t = a.type.get_canonical()
            if t.kind != k.POINTER:
                continue
            p = t.get_pointee().get_canonical()
            if p.kind in (k.FUNCTIONPROTO, k.FUNCTIONNOPROTO):
                d["callback"] = True
            elif p.kind in (k.CHAR_S, k.CHAR_U, k.SCHAR, k.UCHAR) \
                    and not t.get_pointee().is_const_qualified():
                d["wbuf"] = True
            elif p.kind == k.VOID:
                d["voidp"] = True
        out[c.spelling] = d
    return out


def build_ab(sampled):
    m05a = load_mod("05a_extract_bodies.py")
    rows = {"A": {}, "B": {}}
    for lib, names in sampled.items():
        cfg = m05a.LIBS.get(lib)
        if not cfg:
            continue
        shapes = header_shapes(cfg["header"], cfg["args"], set(names))
        for n in names:
            s = shapes.get(n)
            # A binds everything and never permits a free
            rows["A"].setdefault(lib, []).append((n, "library", "", "y", ""))
            if s is None:
                # not visible in the header: a type-directed tool cannot
                # wrap what it cannot see
                rows["B"].setdefault(lib, []).append(
                    (n, "library", "", "n", "not declared in the public header"))
                continue
            why = [w for w, hit in (("function-pointer parameter", s["callback"]),
                                    ("non-const char* parameter", s["wbuf"]),
                                    ("raw void*", s["voidp"]),
                                    ("variadic signature", s["variadic"])) if hit]
            rows["B"].setdefault(lib, []).append(
                (n, "library", "", "n" if why else "y", "; ".join(why)))
    return rows


# ------------------------------------------------------------------- C
def build_c(sampled):
    sys.path.insert(0, ".")
    from src.spec.io import load_yaml
    rows = {}
    for lib, names in sampled.items():
        p = f"snapshots/{lib}_esc.yaml" if os.path.exists(f"snapshots/{lib}_esc.yaml") else f"snapshots/{lib}_audit.yaml"
        if not os.path.exists(p):
            continue
        spec = load_yaml(p)
        for n in names:
            fn = spec.functions.get(n)
            if fn is None:
                # dropped at extraction; their generator never sees it either
                rows.setdefault(lib, []).append((n, "", "", "n", "not extracted"))
                continue
            life = fn.lifecycle or ""
            # no owned-versus-borrowed distinction: anything that hands back a
            # handle is treated as transferring it
            if life in ("creates", "borrows"):
                owner, life = "caller", "creates"
            else:
                owner = "library" if fn.handle_type else ""
            # no abstention: a binding is emitted for every function processed
            rows.setdefault(lib, []).append((n, owner, life, "y", ""))
    return rows


# ------------------------------------------------------------------ run
def write(cfg, rows, strata):
    d = f"{OUT}/{cfg}"
    os.makedirs(d, exist_ok=True)
    for lib, items in rows.items():
        with open(f"{d}/audit_{lib}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            for n, owner, life, bound, reason in items:
                w.writerow({"function": n, "stratum": strata[lib].get(n, ""),
                            "ferrule_owner": owner, "ferrule_lifecycle": life,
                            "ferrule_bound": bound, "refusal_reason": reason})
    return d


def score(d, pattern="audit_{lib}.csv"):
    pairs = []
    for lib in LIBS:
        p = f"{d}/" + pattern.format(lib=lib)
        if os.path.exists(p):
            pairs += ["--pairs", f"{AUDIT}/audit_{lib}_blind.csv:{p}"]
    out = subprocess.run([sys.executable, "eval/04b_tally_audit.py"] + pairs,
                         capture_output=True, text=True).stdout
    row = re.search(r"OVERALL\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", out)
    acc = re.search(r"accuracy\s+([\d.]+)%", out)
    if not row:
        return None
    return dict(n=int(row.group(1)), correct=int(row.group(2)),
                unsafe=int(row.group(3)), leak=int(row.group(4)),
                false_ref=int(row.group(5)), acc=float(acc.group(1)))


def capability(d, labels, pattern="audit_{lib}.csv"):
    """Functions the configuration says the caller may free, and the label agrees."""
    ok = wrong = 0
    for lib in LIBS:
        p = f"{d}/" + pattern.format(lib=lib)
        if not os.path.exists(p):
            continue
        for r in csv.DictReader(open(p)):
            if (r["ferrule_owner"] or "").strip().lower() != "caller":
                continue
            lab = labels[lib].get(r["function"], "")
            if lab == "caller":
                ok += 1
            elif lab in ("library", "shared"):
                wrong += 1
    return ok, wrong


def main():
    sampled, strata, labels = {}, {}, {}
    for lib in LIBS:
        p = f"{AUDIT}/audit_{lib}_blind.csv"
        if not os.path.exists(p):
            continue
        rs = list(csv.DictReader(open(p, newline="")))
        sampled[lib] = [r["function"] for r in rs]
        strata[lib] = {r["function"]: r.get("stratum", "") for r in rs}
        labels[lib] = {r["function"]: (r.get("label_owner") or "").strip().lower()
                       for r in rs}

    ab = build_ab(sampled)
    dirs = {"A": write("A_all_borrow", ab["A"], strata),
            "B": write("B_structural", ab["B"], strata),
            "C": write("C_ravitch", build_c(sampled), strata)}

    names = {"A": "A  all-borrow", "B": "B  structural only",
             "C": "C  Ravitch-style", "D": "D  Ferrule"}
    print(f"\n{'configuration':<22}{'acc':>7}{'unsafe':>8}{'leak':>6}"
          f"{'f-ref':>7}{'freeable':>10}{'wrong free':>12}")
    results = {}
    for cfg in ("A", "B", "C"):
        s = score(dirs[cfg])
        if s is None:
            print(f"  ! {cfg}: scoring failed")
            continue
        ok, wrong = capability(dirs[cfg], labels)
        results[cfg] = (s, ok, wrong)
        print(f"{names[cfg]:<22}{s['acc']:>6.1f}%{s['unsafe']:>8}{s['leak']:>6}"
              f"{s['false_ref']:>7}{ok:>10}{wrong:>12}")

    s = score(AUDIT, "audit_{lib}_key.csv")
    ok, wrong = capability(AUDIT, labels, "audit_{lib}_key.csv")
    if s:
        results["D"] = (s, ok, wrong)
        print(f"{names['D']:<22}{s['acc']:>6.1f}%{s['unsafe']:>8}{s['leak']:>6}"
              f"{s['false_ref']:>7}{ok:>10}{wrong:>12}")

    print("""
freeable    the configuration says owner=caller and the label agrees
wrong free  it says owner=caller and the label says the library owns it:
            each one is an invitation to double free""")
    if "C" in results and "D" in results:
        c, d = results["C"], results["D"]
        print(f"\nabstention costs {c[1] - d[1]} freeable functions and removes "
              f"{c[0]['unsafe'] - d[0]['unsafe']} unsafe verdicts\n"
              f"and {c[2] - d[2]} invitations to double free.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
