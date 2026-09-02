"""
Measure the ownership blind-spot on a type-level spec. A library like libgit2
encodes its lifetime discipline in NAMING (_new/_create/_alloc allocate;
_free/_dispose/_delete destroy; _dup duplicates/refcounts). Without source-level
ownership analysis, the type-level pipeline cannot infer any of it. This script
counts, per spec, how many ownership-relevant functions exist (by name) and how
many actually received a lifecycle/owner annotation -- the gap is the finding.

Usage:
    python3 05_ownership_blindspot.py eval_specs/libgit2_typelevel.spec.yaml
    python3 05_ownership_blindspot.py eval_specs/zlib_typelevel.spec.yaml
"""
import re
import sys
import yaml

CREATE = re.compile(r"_(new|create|alloc|open|dup|clone|copy)\b|_(new|create|alloc|dup)$", re.I)
DESTROY = re.compile(r"_(free|dispose|delete|close|destroy|release|unref)\b|_(free|dispose|delete|destroy)$", re.I)


def main():
    spec = yaml.safe_load(open(sys.argv[1]))
    funcs = spec.get("functions", {}) or {}

    relevant = []          # (name, expected_role, inferred_lifecycle)
    for name, fn in funcs.items():
        life = fn.get("lifecycle") or ""
        owner = fn.get("owner") or ""
        exp = None
        if DESTROY.search(name):
            exp = "destroys"
        elif CREATE.search(name):
            exp = "creates"
        if exp:
            relevant.append((name, exp, life, owner))

    total = len(relevant)
    got_lifecycle = sum(1 for _, _, life, _ in relevant if life)
    correct = sum(1 for _, exp, life, _ in relevant if life == exp)

    print(f"spec: {sys.argv[1]}")
    print(f"total functions in spec           : {len(funcs)}")
    print(f"ownership-relevant by name        : {total}")
    print(f"  ...received ANY lifecycle        : {got_lifecycle}")
    print(f"  ...lifecycle matches name-implied: {correct}")
    print()
    if total:
        print(f"BLIND-SPOT: {total - got_lifecycle}/{total} "
              f"({100.0*(total-got_lifecycle)/total:.0f}%) of ownership-relevant "
              f"functions got NO lifecycle inference at all.")
        print("(This is the type-level ceiling: ownership discipline encoded in")
        print(" naming/refcounting is invisible without source-level analysis,")
        print(" which the amalgamation could not provide for this library.)")
    print()
    print("sample (first 20 relevant functions):")
    for name, exp, life, owner in relevant[:20]:
        mark = "OK " if life == exp else ("~~~" if life else "MISS")
        print(f"  [{mark}] {name:42} name-implies={exp:9} inferred={life or '-':9} owner={owner or '-'}")


if __name__ == "__main__":
    main()
