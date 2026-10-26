#!/usr/bin/env bash
# Regenerate each capability specification from the library sources and compare
# it, function by function, with the snapshot committed at tag eval-frozen.
#
#   bash eval/regenerate_specs.sh                 # all libraries except SQLite
#   bash eval/regenerate_specs.sh sqlite          # SQLite alone (about 30 minutes)
#   bash eval/regenerate_specs.sh cjson zlib      # any subset
#
# Libraries are expected under $FERRULE_LIBS (default ~/ferrule-libs), built at
# the versions listed in REPRODUCE.md.
set -uo pipefail

L=${FERRULE_LIBS:-$HOME/ferrule-libs}
OUT=${FERRULE_REGEN:-/tmp/ferrule-regen}
mkdir -p "$OUT"

Z=$L/zlib; G=$L/libgit2; X=$L/libxml2; S=$L/sqlite
Q=$L/postgresql/src/interfaces/libpq
PQ_INC="-I $L/postgresql/src/include -I $L/postgresql/src/port -I $Q"
ZLIB_SRC=$(for f in adler32 compress crc32 deflate gzclose gzlib gzread gzwrite \
                    infback inffast inflate inftrees trees uncompr zutil; do
             printf -- "--source %s/%s.c " "$Z" "$f"; done)

infer () {   # name snapshot args...
  local name=$1 snap=$2; shift 2
  echo "== $name"
  python3 -m src.cli infer "$@" -o "$OUT/$name.yaml" > "$OUT/$name.log" 2>&1
  python3 - "$snap" "$OUT/$name.yaml" "$OUT/$name.log" "$name" << 'EOF'
import sys, re, yaml
snap, regen, log, name = sys.argv[1:]
try:
    a = yaml.safe_load(open(snap)); b = yaml.safe_load(open(regen))
except FileNotFoundError as e:
    print(f"   {name}: FAILED ({e.filename} missing; see {log})"); sys.exit()
fa, fb = a.get("functions", a), b.get("functions", b)
diff = [n for n in fa if n in fb and fa[n] != fb[n]]
only = sorted(set(fa) ^ set(fb))
m = re.search(r"buildable tools : (\d+)", open(log).read())
ok = not diff and not only
print(f"   {name}: {len(fb)} functions, {len(diff)} differing records, "
      f"{len(only)} only in one, buildable {m.group(1) if m else '?'}  "
      f"{'MATCHES' if ok else 'DIFFERS ' + str((diff + only)[:4])}")
EOF
}

want () { [ $# -eq 0 ] && return 0; for w in "${SELECT[@]}"; do [ "$w" = "$1" ] && return 0; done; return 1; }
SELECT=("$@")
all=$([ ${#SELECT[@]} -eq 0 ] && echo yes || echo no)

if want cjson || [ $all = yes ]; then
  infer cjson snapshots/cjson_esc.yaml \
    "$L/cJSON/cJSON.h" "$L/cJSON/libcjson.so" --source "$L/cJSON/cJSON.c"; fi
if want zlib || [ $all = yes ]; then
  # shellcheck disable=SC2086
  infer zlib snapshots/zlib_esc.yaml \
    "$Z/zlib.h" "$Z/libz.so" $ZLIB_SRC -I "$Z"; fi
if want libpng || [ $all = yes ]; then
  infer libpng snapshots/libpng_esc.yaml \
    "$L/libpng/png.h" "$L/libpng/.libs/libpng16.so" --source-dir "$L/libpng" \
    -I "$L/libpng" -I "$Z"; fi
if want libpq || [ $all = yes ]; then
  # shellcheck disable=SC2086
  infer libpq snapshots/libpq_esc.yaml \
    "$Q/libpq-fe.h" "$Q/libpq.so" --source-dir "$Q" $PQ_INC
  # shellcheck disable=SC2086
  infer libpq_ann snapshots/libpq_ann.yaml \
    "$Q/libpq-fe.h" "$Q/libpq.so" --source-dir "$Q" $PQ_INC \
    --overrides libpq.overrides.yaml; fi
if want libgit2 || [ $all = yes ]; then
  infer libgit2 snapshots/libgit2_esc.yaml \
    "$G/include/git2.h" "$G/build/libgit2.so" --source-dir "$G/src/libgit2" \
    -I "$G/include" -I "$G/src/util" -I "$G/src/libgit2" -I "$G/build/src/util" \
    -I "$G/deps/xdiff" -I "$G/deps/pcre" -I "$G/deps/ntlmclient"; fi
if want libxml2 || [ $all = yes ]; then
  infer libxml2 snapshots/libxml2_esc.yaml \
    "$X/include/libxml/parser.h" "$X/build/libxml2.so" --source-dir "$X" \
    -I "$X/include" -I "$X/build"; fi
if want sqlite; then
  infer sqlite snapshots/sqlite_esc.yaml \
    "$S/sqlite3.h" "$L/libsqlite3.so" --source "$S/sqlite3.c"; fi
