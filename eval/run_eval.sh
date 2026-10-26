#!/usr/bin/env bash
# Run Ferrule on the held-out libraries and STORE structured results.
# Run from the Ferrule repo root (where `python3 -m src.cli` works).
#
# For each library it produces, under eval_results/<lib>/:
#   spec.yaml    the inferred capability spec
#   infer.log    the full stdout/stderr of the run
#   summary.txt  the buildable/refused summary block
# and appends one row to eval_results/coverage.csv
set -uo pipefail

OUT=eval_results
mkdir -p "$OUT"
CSV="$OUT/coverage.csv"
# header once
[ -f "$CSV" ] || echo "library,header,so_present,buildable,refused,skipped_l2,timestamp" > "$CSV"

# resolve system paths (apt-installed)
Z_H=$(find /usr/include -name zlib.h 2>/dev/null | head -1)
Z_SO=$(find /lib /usr/lib -name 'libz.so*' 2>/dev/null | head -1)
G_H=$(find /usr/include -name git2.h 2>/dev/null | head -1)
G_SO=$(find /lib /usr/lib -name 'libgit2.so*' 2>/dev/null | head -1)
PQ_H=$(find /usr/include -name libpq-fe.h 2>/dev/null | head -1)
PQ_SO=$(find /lib /usr/lib -name 'libpq.so*' 2>/dev/null | head -1)
PNG_H=$(find /usr/include -name png.h 2>/dev/null | head -1)
PNG_SO=$(find /lib /usr/lib -name 'libpng*.so*' 2>/dev/null | head -1)

run_one () {
    local name="$1"; local header="$2"; local so="$3"; local incdir="$4"
    local d="$OUT/$name"; mkdir -p "$d"
    echo "=================================================="
    echo " $name"
    echo "=================================================="
    if [ -z "$header" ]; then
        echo "  SKIP: header not found (is the -dev package installed?)"
        echo "$name,NOT_FOUND,no,0,0,0,$(date -Iseconds)" >> "$CSV"
        return
    fi
    # header + .so (verification on). If .so missing, run header-only.
    local so_args=(); local so_flag="no"
    [ -n "$so" ] && { so_args=("$so"); so_flag="yes"; }

    python3 -m src.cli infer "$header" "${so_args[@]}" \
        --engine libclang -I "$incdir" --library-name "$name" \
        -o "$d/spec.yaml" > "$d/infer.log" 2>&1

    # extract the summary block + counts
    grep -E "buildable tools|refused|skipped analyses|^    - " "$d/infer.log" > "$d/summary.txt" 2>/dev/null || true
    local b=$(grep -oE "buildable tools : [0-9]+" "$d/infer.log" | grep -oE "[0-9]+" | head -1)
    local r=$(grep -oE "refused +: [0-9]+" "$d/infer.log" | grep -oE "[0-9]+" | head -1)
    local sk=$(grep -c "skipped" "$d/infer.log")
    b=${b:-0}; r=${r:-0}
    echo "  buildable=$b  refused=$r  (full log: $d/infer.log)"
    echo "$name,$header,$so_flag,$b,$r,$sk,$(date -Iseconds)" >> "$CSV"
}

run_one zlib    "$Z_H"   "$Z_SO"   "$(dirname "${Z_H:-/usr/include}")"
run_one libgit2 "$G_H"   "$G_SO"   "/usr/include"
run_one libpq   "$PQ_H"  "$PQ_SO"  "$(dirname "${PQ_H:-/usr/include}")"
run_one libpng  "$PNG_H" "$PNG_SO" "$(dirname "${PNG_H:-/usr/include}")"

echo
echo "=================================================="
echo " coverage summary ($CSV)"
echo "=================================================="
column -t -s, "$CSV"
