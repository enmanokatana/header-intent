#!/usr/bin/env python3
"""
LLM baseline across providers. Same prompt, same scorer, different vendors.

    # OpenAI
    export OPENAI_API_KEY=...
    python3 eval/05d_llm_multi.py --provider openai --model <model> --tag gpt

    # anything OpenAI-compatible (OpenRouter, DeepSeek, Mistral, Together, local)
    export OPENROUTER_API_KEY=...
    python3 eval/05d_llm_multi.py --provider openai --tag or-llama \\
        --base-url https://openrouter.ai/api/v1 --api-key-env OPENROUTER_API_KEY \\
        --model <model>

    # Google
    export GOOGLE_API_KEY=...
    python3 eval/05d_llm_multi.py --provider google --model <model> --tag gemini

    # prompt ablation: drop the enumerated unsafe categories
    python3 eval/05d_llm_multi.py --provider openai --model <model> \\
        --tag gpt-norubric --no-rubric

Writes snapshots/llm_<tag>/ in the same layout as 05b, so 04b_tally_audit.py
and 05c_llm_agreement.py both work unchanged:

    python3 eval/05c_llm_agreement.py --dir snapshots/llm_<tag>

Why this exists: the first baseline ran on the same vendor's model as the tool
under test, and it BEAT the tool. That is the first thing a reviewer will push
on, and running a second vendor is cheap. Record the exact model strings and
the date in the paper -- these results are not reproducible from a family name.

--no-rubric exists because the shared prompt enumerates the categories that
make a function unsafe to expose (callbacks, writable buffers, variadics,
structs of function pointers), which is close to the labelling sheet's own
rubric. Running with and without measures how much of the model's exposability
performance is inference rather than instruction-following.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import time

AUDIT = "eval_output/audit"
LIBS = ["cjson", "sqlite", "zlib", "libpng", "libpq", "libgit2"]
COLS = ["function", "stratum", "ferrule_owner", "ferrule_lifecycle",
        "ferrule_bound", "refusal_reason"]

RUBRIC = """  safe_to_expose  can a binding expose this function safely at all? Answer "no"
                  for callbacks, writable buffers whose size the caller must
                  supply, variadic parameter lists, and structs containing
                  function pointers."""
NO_RUBRIC = """  safe_to_expose  can an automatic binding expose this function safely at
                  all, given only its signature and body?"""


def load_05b():
    p = os.path.join(os.path.dirname(__file__), "05b_llm_baseline.py")
    spec = importlib.util.spec_from_file_location("llm05b", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def extract_json(text):
    t = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    t = t.strip()
    if not t.startswith("{"):
        i, j = t.find("{"), t.rfind("}")
        if i < 0 or j <= i:
            raise ValueError(f"no JSON object in: {text[:200]}")
        t = t[i:j + 1]
    return json.loads(t)


def make_caller(args, system):
    if args.provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic()

        def call(text):
            r = client.messages.create(model=args.model, max_tokens=500,
                                       system=system,
                                       messages=[{"role": "user", "content": text}])
            return "".join(b.text for b in r.content
                           if getattr(b, "type", "") == "text")
        return call

    if args.provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=os.environ[args.api_key_env],
                        base_url=args.base_url or None)

        def call(text):
            msgs = [{"role": "system", "content": system},
                    {"role": "user", "content": text}]
            try:
                r = client.chat.completions.create(
                    model=args.model, messages=msgs, max_tokens=500)
            except Exception:
                # newer models reject max_tokens in favour of max_completion_tokens
                r = client.chat.completions.create(
                    model=args.model, messages=msgs, max_completion_tokens=500)
            return r.choices[0].message.content or ""
        return call

    if args.provider == "google":
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=os.environ[args.api_key_env])

        def call(text):
            r = client.models.generate_content(
                model=args.model, contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=system, max_output_tokens=500))
            return r.text or ""
        return call

    raise SystemExit(f"unknown provider {args.provider!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True,
                    choices=["openai", "google", "anthropic"])
    ap.add_argument("--model", required=True,
                    help="exact model string; record it in the paper")
    ap.add_argument("--tag", required=True, help="output goes to snapshots/llm_<tag>")
    ap.add_argument("--base-url", default="")
    ap.add_argument("--api-key-env", default="")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--no-rubric", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.api_key_env:
        args.api_key_env = {"openai": "OPENAI_API_KEY",
                            "google": "GOOGLE_API_KEY",
                            "anthropic": "ANTHROPIC_API_KEY"}[args.provider]

    mod = load_05b()
    system = mod.SYSTEM
    if args.no_rubric:
        if RUBRIC not in system:
            print("  ! rubric block not found; prompt may have changed")
        system = system.replace(RUBRIC, NO_RUBRIC)

    bodies = {}
    for lib in LIBS:
        p = f"snapshots/bodies_{lib}.json"
        if os.path.exists(p):
            bodies[lib] = json.load(open(p))
    if not bodies:
        print("run eval/05a_extract_bodies.py first")
        return 1

    out = f"snapshots/llm_{args.tag}"
    if args.dry_run:
        lib = next(iter(bodies)); name = next(iter(bodies[lib]))
        print(f"=== provider {args.provider}  model {args.model}  -> {out} ===")
        print("=== SYSTEM ===\n" + system)
        print("\n=== USER ===\n" + mod.prompt_for(name, bodies[lib][name])[:1500])
        return 0

    call = make_caller(args, system)
    os.makedirs(out, exist_ok=True)
    json.dump({"provider": args.provider, "model": args.model,
               "no_rubric": args.no_rubric, "base_url": args.base_url,
               "when": time.strftime("%Y-%m-%d %H:%M:%S")},
              open(f"{out}/provenance.json", "w"), indent=1)

    for run in range(1, args.runs + 1):
        for lib, info in bodies.items():
            strata = {r["function"]: r.get("stratum", "") for r in
                      csv.DictReader(open(f"{AUDIT}/audit_{lib}_blind.csv",
                                          newline=""))}
            rows, raw, errs = [], {}, 0
            for i, (name, src) in enumerate(info.items(), 1):
                try:
                    a = extract_json(call(mod.prompt_for(name, src)))
                except Exception as e:
                    a = {"owner": "unknown", "lifecycle": "unknown",
                         "safe_to_expose": "unknown", "reason": f"error: {e}"}
                    errs += 1
                raw[name] = a
                owner, life = a.get("owner", "unknown"), a.get("lifecycle", "unknown")
                rows.append({
                    "function": name,
                    "stratum": strata.get(name, ""),
                    "ferrule_owner": "" if owner in ("unknown", "na") else owner,
                    "ferrule_lifecycle": "" if life in ("unknown", "na") else life,
                    "ferrule_bound": "y" if a.get("safe_to_expose") == "yes" else "n",
                    "refusal_reason": "" if a.get("safe_to_expose") == "yes"
                                      else (a.get("reason") or "")[:120],
                })
                print(f"\r  {args.tag} run{run} {lib:<9} {i}/{len(info)}",
                      end="", flush=True)
                if args.sleep:
                    time.sleep(args.sleep)
            with open(f"{out}/audit_{lib}_llm{run}.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=COLS)
                w.writeheader(); w.writerows(rows)
            json.dump(raw, open(f"{out}/raw_{lib}_llm{run}.json", "w"), indent=1)
            print(f"\r  {args.tag} run{run} {lib:<9} {len(rows)} written"
                  + (f", {errs} errors" if errs else "") + " " * 10)

    print(f"\nAccuracy against your labels:\n  python3 eval/04b_tally_audit.py \\")
    print("      " + " \\\n      ".join(
        f"--pairs {AUDIT}/audit_{l}_blind.csv:{out}/audit_{l}_llm1.csv"
        for l in bodies))
    print(f"\nAbstention and agreement:\n  python3 eval/05c_llm_agreement.py --dir {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
