from __future__ import annotations

import ctypes
import inspect
import sys

from ..spec.io import load_yaml
from ..verify.probes import apply_verification
from ..core.invoker import build_capabilities
from ..core.handles import HandleTable


def mcp_return_type(cap) -> type:
    if cap.returns_mapping:
        return dict
    return cap.outputs[0].py_type if cap.outputs else type(None)


def register(mcp, cap) -> None:
    params = [inspect.Parameter(f.name, inspect.Parameter.KEYWORD_ONLY,
                                annotation=f.py_type) for f in cap.inputs]
    ret = mcp_return_type(cap)

    def make(c):
        def fn(**kwargs):
            return c.invoke(**kwargs)
        return fn

    fn = make(cap)
    fn.__name__ = cap.name
    fn.__doc__ = cap.doc
    fn.__signature__ = inspect.Signature(params, return_annotation=ret)
    fn.__annotations__ = {f.name: f.py_type for f in cap.inputs} | {"return": ret}
    mcp.tool(name=cap.name, description=cap.doc)(fn)


def make_server(so_path: str, spec_path: str, name: str = "ferrule", verify: bool = True):
    from mcp.server.fastmcp import FastMCP                                        

    spec = load_yaml(spec_path)
    lib = ctypes.CDLL(so_path)
    if verify:
        apply_verification(lib, spec)

    handles = HandleTable()
    caps, refused = build_capabilities(lib, spec, handles)

                                                                                    
                                                                
    if refused:
        print(f"[ferrule] serving {len(caps)} tools; skipped {len(refused)} refused:",
              file=sys.stderr)
        for n, why in refused:
            print(f"  - {n}: {why}", file=sys.stderr)

    mcp = FastMCP(name)
    for cap in caps:
        register(mcp, cap)
    return mcp


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python -m ferrule.emit.mcp <lib.so> <spec.yaml>", file=sys.stderr)
        raise SystemExit(2)
    make_server(sys.argv[1], sys.argv[2]).run()
