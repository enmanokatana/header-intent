# Reproducing "Inferring C Memory Contracts for Multi-Protocol Reuse"

This guide maps every result in the paper to the revision, inputs, and command
that produce it. All commands run from the repository root.

## 1. Revisions

| Tag | Contents | Produces |
|---|---|---|
| `eval-frozen` | code, capability specifications, labels, and audit keys of 2026-09-29 | audit, coverage, ablation, and language-model results |
| `eval-postfix` | `eval-frozen` plus one runtime fix (`src/core/invoker.py`: input handles in out-handle calls are translated through the handle table) | every executed check: consequences, walkthrough, protocol matrix, tasks, adversarial suite, cost |

Commits after `eval-postfix` add evaluation scripts and data only. This prints
nothing:

    git diff eval-postfix HEAD --stat -- src/

## 2. Environment

- x86-64 Linux; the reported runs used Ubuntu under WSL2 (kernel 6.6, glibc 2.39)
- Python 3.12.3 and `pip install -r requirements.txt`
  (libclang 18.1.1, mcp 1.28.1, grpcio 1.82.1, protobuf 7.35.1, PyYAML 6.0.3, pycparser 3.0)
- gcc, make, cmake
- a local PostgreSQL server for the libpq task only:

      sudo apt install postgresql && sudo -u postgres createuser -s $USER

## 3. Libraries

Libraries live under `~/ferrule-libs` (override with `FERRULE_LIBS`).

| Library | Version | Build |
|---|---|---|
| cJSON | git tag `v1.7.19` | `gcc -shared -fPIC -o libcjson.so cJSON.c` |
| zlib | git tag `v1.3` | project's default build, producing `libz.so` |
| libpng | git tag `v1.6.43` | project's default build, producing `.libs/libpng16.so` |
| PostgreSQL (libpq) | git tag `REL_16_15` | `./configure --without-icu --without-readline --without-zlib`, `make -C src/port pg_config_paths.h`, then the libpq build, producing `src/interfaces/libpq/libpq.so` |
| libgit2 | git tag `v1.7.2` | project's default CMake build in `build/`, producing `build/libgit2.so` |
| libxml2 | git tag `v2.12.6` | in `build/`: `cmake .. -DBUILD_SHARED_LIBS=ON -DLIBXML2_WITH_PYTHON=OFF -DLIBXML2_WITH_LZMA=OFF && make` |
| SQLite | 3.45.1 amalgamation | `gcc -shared -fPIC -O1 -o ~/ferrule-libs/libsqlite3.so sqlite/sqlite3.c -lpthread -ldl -lm` |

## 4. Capability specifications

    bash eval/regenerate_specs.sh            # every library except SQLite
    bash eval/regenerate_specs.sh sqlite     # SQLite alone, the longest run

Each library is regenerated from its sources and compared, function by
function, with the snapshot in `snapshots/` (`*_esc.yaml`, and `libpq_ann.yaml`
for the annotated libpq specification, built with `--overrides
libpq.overrides.yaml`). Every library reports `MATCHES`. The script also prints
each analysis time.

Counting rules for the coverage table:

- **Exported**: functions in the specification plus variadic functions refused
  at extraction (listed under `skipped analyses` in the run log). SQLite: 283 + 8 = 291.
- **Bound**: `buildable tools` in the run log minus generated `alloc_*`
  allocators. libgit2: 674 - 29 = 645.

## 5. Results and the commands that produce them

Library paths below use `L=~/ferrule-libs`.

| Result (paper section) | Inputs | Command |
|---|---|---|
| Verdict accuracy by draw, 81.8% and 53.5% (V-B) | `eval_output/audit/` labels and keys | `python3 eval/04e_split_score.py` |
| Audit categories (V-B) | same | `python3 eval/08_reconcile_audit.py` (the paper's "mismatch, no effect" row merges its over-grant, under-grant, incomplete, and other rows) |
| Consequences of memory-relevant verdicts (V-B) | `snapshots/*_esc.yaml` | `python3 eval/09_runtime_consequences.py --zlib $L/zlib/libz.so:snapshots/zlib_esc.yaml --libgit2 $L/libgit2/build/libgit2.so:snapshots/libgit2_esc.yaml --libpq $L/postgresql/src/interfaces/libpq/libpq.so:snapshots/libpq_esc.yaml` |
| Runtime walkthrough of Example 1 (IV-C) | cJSON | `python3 eval/10_walkthrough_trace.py $L/cJSON/libcjson.so snapshots/cjson_esc.yaml` |
| Signature-only baseline (V-D) | cJSON | `eval/10_naive_ctypes_baseline.py` (usage in its header) |
| Coverage (V-G) | library sources | `bash eval/regenerate_specs.sh` (see section 4) |
| Task coverage, bound (V-G) | specifications | `python3 eval/08_task_coverage.py --repo . --lib <lib> --spec <spec> --so <so>` per library |
| Task coverage, executed (V-G) | specifications, PostgreSQL | `python3 eval/12_task_execution.py --cjson $L/cJSON/libcjson.so:snapshots/cjson_esc.yaml --zlib $L/zlib/libz.so:snapshots/zlib_esc.yaml --libpq $L/postgresql/src/interfaces/libpq/libpq.so:snapshots/libpq_ann.yaml --pg "host=/var/run/postgresql dbname=postgres"` |
| Internal ablation, 206 functions (V-I) | labels, specifications, headers | `python3 eval/07_ablation.py` |
| Learned contracts (V-J) | `snapshots/llm*/` | scored by `python3 eval/06_llm_tables.py`; see section 6 |
| Protocol matrix (V-K) | cJSON | `python3 eval/11_protocol_matrix.py --spec snapshots/cjson_esc.yaml --so $L/cJSON/libcjson.so` |
| Adversarial sequences (V-L) | cJSON, SQLite | `python3 eval/13_adversarial_suite.py --cjson $L/cJSON/libcjson.so:snapshots/cjson_esc.yaml --sqlite $L/libsqlite3.so:snapshots/sqlite_esc.yaml` |
| Runtime cost (V-M) | cJSON | `python3 eval/14_runtime_cost.py $L/cJSON/libcjson.so snapshots/cjson_esc.yaml` and `python3 eval/12_memory_and_aggregate.py memory` |
| Analysis time (V-M) | library sources | printed by `bash eval/regenerate_specs.sh` |
| Regression tests | | `python3 -m pytest -q` (188 tests) |

## 6. Language-model setup

| Run | Model | Prompt | Date | Outputs |
|---|---|---|---|---|
| Claude, criteria given | `claude-sonnet-4-6` (Anthropic) | exposability rules stated | 2026-09-23 | `snapshots/llm/` |
| GPT, criteria given | `gpt-4.1` (OpenAI) | exposability rules stated | 2026-09-23 | `snapshots/llm_gpt/` |
| Claude, criteria withheld | `claude-sonnet-4-6` | no rules | 2026-09-24 | `snapshots/llm_claude-norubric/` |
| GPT, criteria withheld | `gpt-4.1` | no rules | 2026-09-24 | `snapshots/llm_gpt-norubric/` |

Prompts and querying are in `eval/05b_llm_baseline.py` (two runs per condition).
Raw responses (`raw_*.json`) and parsed verdicts (`audit_*_llm{1,2}.csv`) are
committed, so the table can be rescored without API access. Re-querying needs
API keys and may return different answers. `snapshots/llm_v1_promptbug/` holds
an earlier run with a prompt defect and is not used in the paper.

## 7. Known limitations of this package

- Several test files (`tests/test_1.py`, `test_2.py`, `test_arrays.py`,
  `test_ownership.py`, `test_phase2_handles.py`, `test_pipeline.py`) exercise
  the deprecated `src/server/` builder rather than the shared runtime in
  `src/core/` that every adapter uses.
- The deprecated `src/server/mcp_server.py` is not the paper's MCP adapter
  (`src/emit/mcp.py`) and does not implement cascade invalidation.
- `eval/setup_libs.sh` and `eval/run_eval.sh` install and analyse the system
  packages from apt, which are other versions than those evaluated; use
  sections 3 and 4 instead.
