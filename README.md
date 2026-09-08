# Ferrule

Ferrule turns a C library into safe, multi-protocol bindings by *inferring* the
memory intent a C signature cannot express, which pointer is a handle, who owns
it, which `int` is a length, which `T**` returns a fresh handle, and refusing to
bind anything it cannot prove safe. One inferred specification drives bindings
for MCP, plain Python, and gRPC, with ownership safety enforced once, in a
shared core.

> **Fail-safe by design:** a function whose safety cannot be established is
> *refused* with a stated reason, never bound on a guess. A refusal is the tool
> working, not failing.

For the research behind Ferrule, the ownership-inference algorithm, the
cross-library generalization study, the handle-idiom taxonomy, and the design
rationale, see the [project wiki](../../wiki). This README is how to run it.

---

## Install

```bash
python3 -m venv venv && source venv/bin/activate
pip install pyyaml pycparser libclang mcp grpcio grpcio-tools
sudo apt install clang gcc        # clang headers matter; gcc is a fallback
```

Run everything from the repo root; the package imports as `src.*`.

---

## Quickstart

Ferrule has two steps: **infer** a specification from source, then **emit** a
binding from it.

**Infer** (single-file / amalgamated library):
```bash
python3 -m src.cli infer <header.h> <library.so> \
    --source <library.c> --engine libclang -I <include-dir> \
    --library-name <name> -o <name>.spec.yaml
```

**Infer** (multi-file library, point at the source tree):
```bash
python3 -m src.cli infer <header.h> <library.so> \
    --source-dir <src/> --engine libclang -I <inc/> \
    --library-name <name> -o <name>.spec.yaml
```

The report lists **buildable** functions, **refused** ones with reasons, the
inferred lifecycles and ownership verdicts, and any source files skipped
(non-fatal). `.so` and `--source` are both optional: omitting the `.so` skips
behavioral verification; omitting source skips ownership analysis. Each
degrades gracefully and is reported.

**Emit** a binding:
```bash
python3 -m src.cli emit <name>.spec.yaml <library.so> --target list     # preview
python3 -m src.cli emit <name>.spec.yaml <library.so> --target python -o bind.py
python3 -m src.cli emit <name>.spec.yaml <library.so> --target proto -o svc.proto
```

**Serve** (optional):
```bash
# MCP Inspector
npx @modelcontextprotocol/inspector python3 -m src.emit.mcp <library.so> <name>.spec.yaml

# plain Python
python3 -c "from src.emit.python import bind_module; m = bind_module('lib.so','name.spec.yaml')"

# gRPC: emit proto -> protoc -> build a server with src.emit.grpc_server
```

---

## CLI reference

| Command | Purpose |
|---|---|
| `infer <header> [lib.so] [--source F \| --source-dir D] -o spec.yaml` | source -> capability specification |
| `emit <spec.yaml> [lib.so] --target list\|python\|proto` | specification -> a binding |
| `verify <lib.so> <spec.yaml>` | re-run behavioral probes, update `verified` flags |

Flags: `--engine libclang` (recommended) or `pycparser`; `-I <dir>` (repeatable)
for includes; `--source` (repeatable) and `--source-dir` for multi-file source;
`--library-name`, `-o`.

---

## Repository layout

```
src/model/extract.py     L0  signature extraction (libclang)
src/layers/              L1 + L2 analyses (intent, handles, ownership, arrays, out-handles)
src/fuse/                merge per-layer facts
src/verify/              behavioral verification against the compiled .so
src/core/                protocol-neutral core: policy (fail-safe gate),
                         handle table (ownership enforced), invoker
src/emit/                thin adapters: mcp, python, proto/grpc_server
src/reuse/               test-suite-reuse classifier
src/pipeline.py, cli.py  orchestration + CLI
tests/                   regression tests (compile real .so; gcc required)
eval/                    reproduce the multi-library evaluation
```

---


## Tests

```bash
pip install pytest && pytest tests/ -v
```
Tests compile small `.so` files with `gcc` and exercise real machine code, not
mocks.

---

## Troubleshooting

- **A function is refused.** Read the reason string; it names the exact
  unsupported idiom (opaque param, callback, writable buffer, raw `void*`
  return). Refusal is the fail-safe, not an error.
- **`parse failed / truncated`.** libclang could not find a header. Pass the
  missing include with `-I`, or the library's build-generated headers (run its
  `./configure`/`cmake` first). See the wiki's *Limitations* page.
- **`.so` won't load.** A version/ABI mismatch; use the header and `.so` from
  the same install, or run static-only by omitting the `.so`.

---

## Citing

If you use Ferrule in academic work, please cite the accompanying paper
(see the wiki's *Paper* page for the reference).