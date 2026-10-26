"""
Task coverage.  (fix F16)

Coverage percentages do not answer the only question a user has: can I do the thing
the library exists for, using only what was bound? A binding that refuses everything
scores perfectly on every safety measure in the paper and compresses nothing.

Each task is an ordered list of the C functions a competent user would call. A task
passes iff every function in it is bound. When it fails, the script names the first
blocker AND its refusal reason, which is the sentence the paper wants.

The zlib entry is the one to look at: deflateInit2_/deflate/inflate all take a
caller-allocated z_stream*, which the role model classifies opaque, so the binding is
safe and cannot compress a byte. Report it; a reviewer finds it in thirty seconds.

Usage
-----
    python3 08_task_coverage.py --repo /path/to/header-intent \\
        --lib cjson  --spec eval_results/cjson/spec.yaml  --so .../libcjson.so \\
        --lib sqlite --spec eval_results/sqlite/spec.yaml --so .../libsqlite3.so \\
        --latex taskcov_table.tex
"""
from __future__ import annotations

import argparse
import ctypes
import sys

TASKS = {
    "cjson": ("parse a document, read a nested field, print it, free it", [
        "cJSON_Parse", "cJSON_GetObjectItem", "cJSON_GetStringValue",
        "cJSON_Print", "cJSON_Delete"]),
    "sqlite": ("open, create+insert, select via prepare/step/column, close", [
        "sqlite3_open", "sqlite3_exec", "sqlite3_prepare_v2", "sqlite3_step",
        "sqlite3_column_int", "sqlite3_column_text", "sqlite3_finalize",
        "sqlite3_close"]),
    "zlib": ("compress a buffer and decompress it again", [
        "deflateInit2_", "deflate", "deflateEnd",
        "inflateInit2_", "inflate", "inflateEnd"]),
    "libpng": ("read a PNG header and its pixel rows", [
        "png_create_read_struct", "png_create_info_struct", "png_init_io",
        "png_read_info", "png_get_image_width", "png_get_image_height",
        "png_read_image", "png_destroy_read_struct"]),
    "libpq": ("connect, run a query, read a field, clean up", [
        "PQconnectdb", "PQstatus", "PQexec", "PQresultStatus", "PQgetvalue",
        "PQclear", "PQfinish"]),
    "libgit2": ("init, open a repo, resolve HEAD, free, shutdown", [
        "git_libgit2_init", "git_repository_open", "git_repository_head",
        "git_reference_name", "git_reference_free", "git_repository_free",
        "git_libgit2_shutdown"]),
}


def bound_and_reasons(repo, spec_path, so_path):
    sys.path.insert(0, repo)
    from src.spec.io import load_yaml
    from src.core.invoker import build_capabilities
    from src.core.handles import HandleTable
    from src.core.policy import check_exposable, SpecViolation

    spec = load_yaml(spec_path)
    lib = ctypes.CDLL(so_path)
    caps, _ = build_capabilities(lib, spec, HandleTable())
    bound = {c.name for c in caps}

    reasons = {}
    for name, fn in spec.functions.items():
        if name in bound:
            continue
        try:
            check_exposable(fn)
            reasons[name] = "not built (no capability path)"
        except SpecViolation as e:
            reasons[name] = str(e).split(":", 1)[-1].strip()
    missing_from_spec = "absent from spec (not extracted)"
    return spec, bound, reasons, missing_from_spec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--lib", action="append", required=True)
    ap.add_argument("--spec", action="append", required=True)
    ap.add_argument("--so", action="append", required=True)
    ap.add_argument("--latex")
    args = ap.parse_args()

    rows = []
    for lib, spec_path, so in zip(args.lib, args.spec, args.so):
        desc, calls = TASKS[lib]
        spec, bound, reasons, absent = bound_and_reasons(args.repo, spec_path, so)
        blocker = None
        for fn in calls:
            if fn in bound:
                continue
            blocker = (fn, reasons.get(fn, absent))
            break
        ok = blocker is None
        rows.append((lib, desc, ok, blocker, len(calls),
                     sum(1 for f in calls if f in bound)))
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {lib:8} {sum(1 for f in calls if f in bound)}/{len(calls)} "
              f"calls bound -- {desc}")
        if blocker:
            print(f"         first blocker: {blocker[0]}  ({blocker[1]})")

    passed = sum(1 for r in rows if r[2])
    print(f"\n{passed}/{len(rows)} libraries can complete their task using only bound "
          f"functions.")

    if args.latex:
        with open(args.latex, "w") as f:
            for lib, desc, ok, blocker, total, got in rows:
                b = "--" if ok else f"\\texttt{{{blocker[0].replace('_', chr(92)+'_')}}}"
                f.write(f"{lib} & {desc} & {'yes' if ok else 'no'} ({got}/{total}) & {b} \\\\\n")
        print(f"wrote {args.latex}")


if __name__ == "__main__":
    main()
