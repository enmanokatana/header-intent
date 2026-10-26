"""
Read the stored specs under eval_results/<lib>/spec.yaml and produce the
per-library breakdown that feeds the paper's evaluation tables:
  - total functions, buildable (have no refuse-worthy trait), 
  - how many got a handle lifecycle (creates/uses/destroys),
  - how many got an ownership verdict (caller/library),
  - ownership-relevant-by-name count and how many got ANY lifecycle
    (the blind-spot measure).

Usage:
    python3 aggregate.py eval_results/*/spec.yaml
"""
import re
import sys
import yaml

CREATE = re.compile(r"_(new|create|alloc|open|dup|clone|init)\b|(new|create|alloc|dup|init)$", re.I)
DESTROY = re.compile(r"_(free|dispose|delete|close|destroy|release|unref|finish|clear|end)\b", re.I)


def analyze(path):
    spec = yaml.safe_load(open(path)) or {}
    funcs = spec.get("functions", {}) or {}
    lib = spec.get("library", path)

    total = len(funcs)
    with_lifecycle = sum(1 for f in funcs.values() if f.get("lifecycle"))
    with_owner = sum(1 for f in funcs.values() if f.get("owner"))
    creates = sum(1 for f in funcs.values() if f.get("lifecycle") == "creates")
    destroys = sum(1 for f in funcs.values() if f.get("lifecycle") == "destroys")

    # ownership-relevant by naming, and how many got any lifecycle (blind-spot)
    rel = [n for n in funcs if CREATE.search(n) or DESTROY.search(n)]
    rel_with_life = sum(1 for n in rel if funcs[n].get("lifecycle"))

    return {
        "library": lib, "total": total,
        "lifecycle": with_lifecycle, "owner": with_owner,
        "creates": creates, "destroys": destroys,
        "ownership_relevant": len(rel), "rel_with_lifecycle": rel_with_life,
    }


def main():
    rows = [analyze(p) for p in sys.argv[1:]]
    cols = ["library", "total", "lifecycle", "owner", "creates", "destroys",
            "ownership_relevant", "rel_with_lifecycle"]
    w = max(len(c) for c in cols)
    print("  ".join(c.rjust(w) if c != "library" else c.ljust(12) for c in cols))
    print("-" * 90)
    for r in rows:
        cells = [str(r["library"]).ljust(12)] + [str(r[c]).rjust(w) for c in cols[1:]]
        print("  ".join(cells))
    print()
    print("Reading guide:")
    print("  lifecycle/owner   = functions that got handle/ownership inference (needs source)")
    print("  ownership_relevant vs rel_with_lifecycle = the blind-spot: how many")
    print("    ownership-named functions actually received a lifecycle verdict.")


if __name__ == "__main__":
    main()
