
## 1. Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install pyyaml pycparser libclang mcp grpcio grpcio-tools
```

You'll also want a working gcc (it's used to compile test .so files, and its
bundled stddef.h is a useful fallback for libclang) and ideally the clang
binary itself (sudo apt install clang), though there's a gcc-based fallback
if you don't have clang.

Everything below assumes you're running from the repo root, with the package
living under `src/` and imported as `src.*` (e.g. `python3 -m src.cli infer ...`).
That's the layout I've been using this whole time, so copy things in as-is.

---

## 2. The core workflow: infer, then emit

### Step 1, infer a capability spec from a real library

```bash
python3 -m src.cli infer <header.h> <library.so> \
    --source <library.c> --engine libclang -I <include-dir> \
    --library-name <name> -o <name>.spec.yaml
```

Example, cJSON:

```bash
git clone --depth 1 https://github.com/DaveGamble/cJSON /tmp/cjson
gcc -shared -fPIC -o /tmp/cjson/libcjson.so /tmp/cjson/cJSON.c

python3 -m src.cli infer /tmp/cjson/cJSON.h /tmp/cjson/libcjson.so \
    --source /tmp/cjson/cJSON.c --engine libclang -I /tmp/cjson \
    --library-name cjson -o cjson.spec.yaml
```

This prints a report: which functions are buildable, which are refused (and
why, every refusal has a specific reason string), the inferred handle
lifecycle, ownership verdicts, and anything skipped. It writes the full spec
to `cjson.spec.yaml`.

A refusal is not a bug. The whole point here is to refuse to bind anything
that can't be verified as safe (raw void* returns, write buffers, callbacks,
unresolved pointers). If a fix makes the refused list grow, that's usually
the fail-safe doing its job correctly, not a regression, so don't panic when
you see it.

### Step 2, emit a protocol target from the spec

```bash
python3 -m src.cli emit <name>.spec.yaml <library.so> \
    --target proto|python|list [--package NAME] [--service NAME] [-o OUTFILE]
```

- `--target list` just prints every buildable capability and its shape. Good
  first sanity check.
- `--target python` emits a plain, readable .py file with real function
  signatures, generated straight from the spec.
- `--target proto` emits a .proto file (see the gRPC section below).

### Step 3, optional, re-verify a spec against a .so

```bash
python3 -m src.cli verify <library.so> <name>.spec.yaml
```

Re-runs the behavioral probes (does an inferred out param actually get
written to, etc) and updates the spec's verified flags in place.

---

## 3. Serving it over a real protocol

### MCP

```bash
npx @modelcontextprotocol/inspector \
    python3 -m src.emit.mcp <library.so> <name>.spec.yaml
```

Opens the MCP Inspector UI where you can call each tool directly. Worth
trying on cJSON: cJSON_Parse, then cJSON_Print, then cJSON_GetObjectItem
(comes back borrowed: true), then try to cJSON_Delete that borrowed handle
(should be refused), then cJSON_Delete the root (frees cleanly). That
refusal is the double free protection actually working.

### gRPC

```bash
# 1. generate the .proto
python3 -m src.cli emit cjson.spec.yaml /tmp/cjson/libcjson.so \
    --target proto --package cjson --service CJson -o cjson.proto

# 2. generate the python stubs
pip install grpcio grpcio-tools
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. cjson.proto

# 3. run the server (edit SO/SPEC/PORT at the top of serve_cjson.py first)
python3 serve_cjson.py

# 4. in another terminal, run the demo client
python3 grpc_client_demo.py
```

grpc_client_demo.py runs the same parse, print, borrowed get, refused
delete, clean delete sequence as the MCP walkthrough, but over a real
network channel. That's the proof the safety guarantee holds no matter the
protocol, since it's enforced once in core/, not per emitter.

One note on gRPC sessions: handles are scoped to a session (OpenSession /
CloseSession), since gRPC doesn't have the single long lived process MCP
gets for free. Pure functions that never touch a handle don't need a
session at all, the .proto marks them stateless.

### Plain Python

```python
from src.emit.python import bind_module
m = bind_module("/tmp/cjson/libcjson.so", "cjson.spec.yaml")
root = m.cJSON_Parse(value='{"a":1}')
print(m.cJSON_Print(handle=root["handle"]))
```

No protocol at all, useful for embedding or just as the cheapest way to
sanity check a spec.

---

## 4. Running the tests

```bash
pip install pytest
pytest tests/ -v
```

Some tests compile small synthetic .so files on the fly (gcc required) to
test against real compiled code instead of mocks. That's deliberate, a
handful of real bugs in this project were only ever caught by compiling and
running actual machine code, not by unit testing the analysis logic alone.

Files worth knowing about specifically:

| File | Covers |
|---|---|
| test_ownership_loose_ends.py | ownership transfer detection, returned string auto free |
| test_out_handle.py, test_out_handle_confirmation.py | the sqlite3_open(path, &db) out param handle idiom |
| test_naming_conventions.py | camelCase vs snake_case allocator/deallocator name recognition |
| test_core_emitters.py, test_emit_proto.py | the protocol agnostic core plus MCP/gRPC emitters, including that ownership enforcement holds with zero protocol specific safety code |

---

## 5. The diag_*.py scripts

These are one off diagnostics I built while chasing specific libclang
AST-shape bugs against real sqlite3 and cJSON source. They're not part of
the library itself, they're debugging tools I'm keeping around in case I
(or you) hit a similar wall extending this to a new library. Run any of them
directly:

```bash
python3 diag_ownership.py          # dump raw and classified ownership verdicts for a function set
python3 diag_returns.py            # inspect every return statement in a function, with raw tokens
python3 diag_body.py               # check whether libclang actually saw a function's full body
python3 diag_out_handle.py         # check L0's out param handle CANDIDATE detection
python3 diag_out_handle_confirm.py # check L2's out param handle CONFIRMATION (the harder part)
python3 diag_open_database.py      # dump every assignment in a specific function, in source order
```


