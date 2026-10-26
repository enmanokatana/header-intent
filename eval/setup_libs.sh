#!/usr/bin/env bash
# Fetch/install the held-out evaluation libraries. Uses apt where possible so we
# get a loadable system .so + headers (no build-from-source fights). Run once.
#   sudo bash setup_libs.sh
set -uo pipefail

echo "=== installing dev packages (headers + loadable .so) ==="
sudo apt-get update -qq
sudo apt-get install -y \
    zlib1g-dev \
    libgit2-dev \
    libpq-dev \
    libpng-dev \
    2>&1 | tail -5

echo
echo "=== locating each library's header + .so ==="
locate_lib () {
    local name="$1"; local header_glob="$2"; local so_name="$3"
    local h=$(find /usr/include -name "$header_glob" 2>/dev/null | head -1)
    local s=$(find /lib /usr/lib -name "$so_name" 2>/dev/null | head -1)
    printf "%-10s header=%-45s so=%s\n" "$name" "${h:-NOT FOUND}" "${s:-NOT FOUND}"
}
locate_lib zlib    "zlib.h"     "libz.so*"
locate_lib libgit2 "git2.h"     "libgit2.so*"
locate_lib libpq   "libpq-fe.h" "libpq.so*"
locate_lib libpng  "png.h"      "libpng*.so*"

echo
echo "Done. Note the header/so paths above; run_eval.sh uses them."
