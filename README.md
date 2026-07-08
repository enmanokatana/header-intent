# Ferrule (header-intent)

Ferrule turns C library signatures and source behavior into an evidenced capability spec, verifies risky pointer claims against the real `.so`, and builds spec-driven call surfaces (including MCP tools).

The core design choice is simple: every semantic fact carries provenance, confidence, and verification state, so the runtime can refuse unsafe guesses instead of silently exposing them.

## What This Repo Does

- Infers a first-pass spec from parsed C signatures (L1).
- Refines pointer intent from function-body behavior when C source is available (L2 static def-use).
- Fuses evidence from multiple layers with conflict tracking.
- Probes inferred `out` and `inout` params against the compiled library.
- Builds tools from spec facts, with fail-safe checks on low-confidence or opaque parameters.

## Current Status

- L1 signature inference is implemented and used by the CLI.
- L2 static analysis (`in`/`out`/`inout`) is implemented in library code.
- L2 handle lifecycle analysis (`creates`/`uses`/`destroys`) is implemented in library code.
- Fusion and conflict reporting are implemented.
- Behavioral verification is implemented.
- MCP server wrapper is implemented.
- Some planned surfaces are still placeholders (`src/layers/l3_naming.py`, `src/layers/l4_docs.py`, and several files under `src/mcp/`).

## Repository Layout

- `src/cli.py`: `infer` and `verify` commands.
- `src/spec/`: schema, vocabulary, YAML I/O.
- `src/layers/l1_signature.py`: signature-to-spec conversion.
- `src/layers/l2_static.py`: source def-use pointer intent analysis.
- `src/layers/l2_handles.py`: source-based handle lifecycle analysis.
- `src/fuse/fusion.py`: evidence fusion and conflict handling.
- `src/verify/probes.py`: behavioral verification gate.
- `src/server/build.py`: spec-driven tool generation + fail-safe checks.
- `src/server/mcp_server.py`: FastMCP registration wrapper.
- `tests/`: phase-oriented and feature tests.
- `docs/`: design notes, runnable entrypoints, verification details.

## Requirements

Minimum runtime:

- Python 3.10+
- `pyyaml`
- `pycparser`

For tests:

- `pytest`
- `gcc` (tests compile tiny shared libraries)

For CLI `infer` from real headers:

- `header_parser_cast` importable on `PYTHONPATH` (from the cToMcp toolkit)

For MCP serving:

- `mcp` package

Optional (for direct libclang-based source analysis):

- `libclang` Python bindings (`pip install libclang`)

## Quick Start

From the repo root:

```bash
python -m venv venv
. venv/bin/activate
pip install pyyaml pycparser pytest
```

Run tests:

```bash
./venv/bin/pytest -q
```

## CLI Usage

The main entrypoint is `src.cli`.

### 1) Infer a spec from a header

```bash
python -m src.cli infer <header.h> [lib.so] [--overrides overrides.yaml] [--library-name NAME] [-o spec.yaml]
```

Notes:

- This command imports `header_parser_cast.parse_header` at runtime.
- If optional `lib.so` is provided, behavioral verification runs before output.

### 2) Verify an existing spec against a real library

```bash
python -m src.cli verify <lib.so> <spec.yaml>
```

This updates `verified` and `confidence` fields in place based on probe results.

## MCP Server

Serve generated tools from a `.so` + spec:

```bash
python -m src.server.mcp_server <lib.so> <spec.yaml>
```

At startup, the server loads the spec, runs verification, builds tools, and registers them with FastMCP.

## Static Analysis in Practice

`l2_static` classifies pointer params by first access to pointee in program order:

- write first -> `out`
- read first then write -> `inout`
- read only -> `in`

Read the detailed walkthrough and diagram:

- `docs/l2_static_read_write_intent.md`

## Safety Model

Two guards prevent unsafe tool exposure:

- Behavioral gate: inferred pointer-write facts must be observed at runtime to be promoted.
- Build-time fail-safe: low-confidence/unverified or opaque params are refused with `SpecViolation`.

This keeps generation conservative by default.


## Development Notes

- Keep specs checked in when useful for reproducibility (`*.spec.yaml`).
- Prefer adding evidence sources over hardcoding behavior in server code.
- If a new inference signal is uncertain, emit it with lower confidence and let verification/fail-safe policy decide.

