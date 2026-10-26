#!/usr/bin/env python3
"""
LLM baseline: ask a frontier model for the same three verdicts, twice.

    export ANTHROPIC_API_KEY=...
    python3 eval/05b_llm_baseline.py --model claude-sonnet-4-6 --runs 2
    python3 eval/05b_llm_baseline.py --dry-run          # print one prompt, call nothing

Writes, per library and run:
    snapshots/llm/audit_<lib>_llm<N>.csv   key format, so 04b_tally_audit.py
                                           scores it against YOUR labels unchanged
    snapshots/llm/raw_<lib>_llm<N>.json    the model's actual answers, including
                                           "unknown", which the CSV flattens

Fairness, since this is the comparison II-E currently only asserts:

  * The model gets the SAME input Ferrule gets -- public declaration plus
    implementation body -- not just the header.
  * "unknown" is offered explicitly and described as preferable to guessing.
    Without that, "it never abstains" would be an artifact of the prompt
    rather than a property of the method.
  * It never sees Ferrule's verdicts, the same blind discipline as the
    human labelling.
  * Two runs of an identical prompt measure run-to-run agreement, which is
    the other half of the claim.

Scoring maps the model's answers onto the key columns:
    owner/lifecycle    -> ferrule_owner / ferrule_lifecycle ("unknown" -> "")
    safe_to_expose     -> ferrule_bound  (yes -> y, otherwise n)
so an abstention reads as a refusal, which is how Ferrule would behave.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time

AUDIT = "eval_output/audit"
OUT = "snapshots/llm"
LIBS = ["cjson", "sqlite", "zlib", "libpng", "libpq", "libgit2"]
COLS = ["function", "stratum", "ferrule_owner", "ferrule_lifecycle",
        "ferrule_bound", "refusal_reason"]

SYSTEM = """You are analysing a C library function to decide its memory contract \
for an automatic binding generator.

Answer with a single JSON object and nothing else:

{"owner": "caller" | "library" | "na" | "unknown",
 "lifecycle": "creates" | "uses" | "destroys" | "na" | "unknown",
 "safe_to_expose": "yes" | "no" | "unknown",
 "reason": "<one sentence>"}

Definitions:
  owner=caller    the caller must eventually free the returned pointer
  owner=library   the library retains ownership; freeing it would be a bug
  owner=na        ownership does not apply (the function returns no pointer)
  owner=unknown   it DOES apply, but the evidence does not settle which
  lifecycle       does this function create, merely use, or destroy a handle,
                  or is it unrelated to any handle (na)
  safe_to_expose  can a binding expose this function safely at all? Answer "no"
                  for callbacks, writable buffers whose size the caller must
                  supply, variadic parameter lists, and structs containing
                  function pointers.

"unknown" is a legitimate and preferred answer wherever the evidence does not \
settle the question. A wrong confident verdict on ownership causes a double \
free or a leak; saying "unknown" costs nothing. Do not guess to appear helpful.

Keep "na" and "unknown" distinct. "na" means the question does not arise for \
this function; "unknown" means it arises and you cannot answer it."""


def prompt_for(name, info):
    parts = [f"Function: {name}"]
    if info.get("decl"):
        parts.append(f"\nPublic declaration:\n{info['decl']}")
    if info.get("body"):
        body = info["body"]
        if len(body) > 12000:
            body = body[:12000] + "\n/* ... truncated ... */"
        parts.append(f"\nImplementation ({info.get('file') or 'source'}):\n{body}")
    else:
        parts.append("\nImplementation: not available.")
    return "\n".join(parts)


def ask(client, model, text):
    r = client.messages.create(
        model=model, max_tokens=400, system=SYSTEM,
        messages=[{"role": "user", "content": text}])
    out = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    out = out.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return json.loads(out.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-sonnet-4-6",
                    help="record this exact string in the paper")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.0)
    args = ap.parse_args()

    bodies = {}
    for lib in LIBS:
        p = f"snapshots/bodies_{lib}.json"
        if os.path.exists(p):
            bodies[lib] = json.load(open(p))
    if not bodies:
        print("No snapshots/bodies_*.json -- run 05a_extract_bodies.py first")
        return 1

    if args.dry_run:
        lib = next(iter(bodies))
        name = next(iter(bodies[lib]))
        print("=== SYSTEM ===\n" + SYSTEM)
        print("\n=== USER ===\n" + prompt_for(name, bodies[lib][name])[:2000])
        return 0

    try:
        import anthropic
    except ImportError:
        print("pip install anthropic")
        return 1
    client = anthropic.Anthropic()
    os.makedirs(OUT, exist_ok=True)

    for run in range(1, args.runs + 1):
        for lib, info in bodies.items():
            blind = f"{AUDIT}/audit_{lib}_blind.csv"
            strata = {r["function"]: r.get("stratum", "")
                      for r in csv.DictReader(open(blind, newline=""))}
            rows, raw = [], {}
            for i, (name, src) in enumerate(info.items(), 1):
                try:
                    a = ask(client, args.model, prompt_for(name, src))
                except Exception as e:
                    a = {"owner": "unknown", "lifecycle": "unknown",
                         "safe_to_expose": "unknown", "reason": f"error: {e}"}
                raw[name] = a
                owner = a.get("owner", "unknown")
                life = a.get("lifecycle", "unknown")
                rows.append({
                    "function": name,
                    "stratum": strata.get(name, ""),
                    # `na` and `unknown` both become an empty column, which is
                    # how Ferrule writes "no verdict" -- so both systems are
                    # scored on identical terms. The raw JSON keeps them apart
                    # for the abstention measure.
                    "ferrule_owner": "" if owner in ("unknown", "na") else owner,
                    "ferrule_lifecycle": "" if life in ("unknown", "na") else life,
                    "ferrule_bound": "y" if a.get("safe_to_expose") == "yes" else "n",
                    "refusal_reason": "" if a.get("safe_to_expose") == "yes"
                                      else (a.get("reason") or "")[:120],
                })
                print(f"\r  run{run} {lib:<9} {i}/{len(info)}", end="", flush=True)
                if args.sleep:
                    time.sleep(args.sleep)
            with open(f"{OUT}/audit_{lib}_llm{run}.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=COLS)
                w.writeheader(); w.writerows(rows)
            json.dump(raw, open(f"{OUT}/raw_{lib}_llm{run}.json", "w"), indent=1)
            print(f"\r  run{run} {lib:<9} {len(rows)} written" + " " * 12)

    print("\nScore it against your labels with the existing scorer:")
    print("  python3 eval/04b_tally_audit.py \\")
    print("      " + " \\\n      ".join(
        f"--pairs {AUDIT}/audit_{l}_blind.csv:{OUT}/audit_{l}_llm1.csv"
        for l in bodies))
    print("\nThen compare the two runs:  python3 eval/05c_llm_agreement.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
