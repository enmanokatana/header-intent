#!/usr/bin/env python3
"""
Retry the calls that failed, in place.

    python3 eval/05e_retry_errors.py --dir snapshots/llm_gpt \\
        --provider openai --model gpt-4.1

05b/05d record a failed call as {"reason": "error: ..."} with every field set
to "unknown". That was the wrong default: it makes a transport failure
indistinguishable from the model declining to answer, which is precisely the
property the abstention measure exists to report. This re-asks only the failed
entries and rewrites both the raw JSON and the CSV.

Entries that still fail keep their error marker, and 05c (once patched)
excludes them from abstention and agreement rather than scoring them.
"""
from __future__ import annotations

import argparse
import csv
import glob
import importlib.util
import json
import os
import re
import time

COLS = ["function", "stratum", "ferrule_owner", "ferrule_lifecycle",
        "ferrule_bound", "refusal_reason"]


def load(name):
    p = os.path.join(os.path.dirname(__file__), name)
    spec = importlib.util.spec_from_file_location(name.replace(".", "_"), p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--provider", required=True,
                    choices=["openai", "google", "anthropic"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-url", default="")
    ap.add_argument("--api-key-env", default="")
    ap.add_argument("--no-rubric", action="store_true")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--sleep", type=float, default=2.0)
    args = ap.parse_args()
    if not args.api_key_env:
        args.api_key_env = {"openai": "OPENAI_API_KEY",
                            "google": "GOOGLE_API_KEY",
                            "anthropic": "ANTHROPIC_API_KEY"}[args.provider]

    m05b, m05d = load("05b_llm_baseline.py"), load("05d_llm_multi.py")
    system = m05b.SYSTEM
    if args.no_rubric:
        system = system.replace(m05d.RUBRIC, m05d.NO_RUBRIC)
    call = m05d.make_caller(args, system)

    bodies = {lib: json.load(open(f"snapshots/bodies_{lib}.json"))
              for lib in ["cjson", "sqlite", "zlib", "libpng", "libpq", "libgit2"]
              if os.path.exists(f"snapshots/bodies_{lib}.json")}

    fixed = still = 0
    for raw_p in sorted(glob.glob(f"{args.dir}/raw_*_llm*.json")):
        m = re.search(r"raw_(\w+)_llm(\d+)\.json$", raw_p)
        lib, run = m.group(1), m.group(2)
        raw = json.load(open(raw_p))
        bad = [n for n, a in raw.items()
               if str(a.get("reason", "")).startswith("error:")]
        if not bad:
            continue
        print(f"  {lib} run{run}: {len(bad)} to retry")
        for n in bad:
            for attempt in range(1, args.attempts + 1):
                try:
                    raw[n] = m05d.extract_json(
                        call(m05b.prompt_for(n, bodies[lib][n])))
                    fixed += 1
                    print(f"    ok   {n}")
                    break
                except Exception as e:
                    if attempt == args.attempts:
                        raw[n]["reason"] = f"error: {e}"
                        still += 1
                        print(f"    FAIL {n}: {str(e)[:80]}")
                    else:
                        time.sleep(args.sleep * attempt)
        json.dump(raw, open(raw_p, "w"), indent=1)

        csv_p = f"{args.dir}/audit_{lib}_llm{run}.csv"
        rows = list(csv.DictReader(open(csv_p, newline="")))
        for r in rows:
            a = raw.get(r["function"])
            if not a:
                continue
            owner, life = a.get("owner", "unknown"), a.get("lifecycle", "unknown")
            r["ferrule_owner"] = "" if owner in ("unknown", "na") else owner
            r["ferrule_lifecycle"] = "" if life in ("unknown", "na") else life
            r["ferrule_bound"] = "y" if a.get("safe_to_expose") == "yes" else "n"
            r["refusal_reason"] = ("" if a.get("safe_to_expose") == "yes"
                                   else (a.get("reason") or "")[:120])
        with open(csv_p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader(); w.writerows(rows)

    print(f"\n{fixed} recovered, {still} still failing")
    if still:
        print("Persistent failures are a real asymmetry between providers "
              "and belong in the write-up, not in the abstention count.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
