"""
DEPRECATED: This module is deprecated and will be removed 
"""
import ctypes
import inspect
import sys

from ..spec.io import load_yaml
from ..verify.probes import apply_verification
from .build import build_tool, SpecViolation
from .handles import HandleTable


def make_server(so_path: str, spec_path: str, name: str = "ferrule"):
    from mcp.server.fastmcp import FastMCP    

    lib = ctypes.CDLL(so_path)
    spec = load_yaml(spec_path)
    apply_verification(lib, spec)              

    mcp = FastMCP(name)
    handles = HandleTable()

    tools, refused = [], []
    for fn in spec.functions.values():
        try:
            tools.append(build_tool(lib, fn, handles))
        except SpecViolation as e:
            refused.append(f"{fn.name}: {str(e).split(';')[0]}")
        except Exception as e:
            refused.append(f"{fn.name}: {type(e).__name__}: {e}")
    if refused:
        print(f"[ferrule] serving {len(tools)} tools; skipped {len(refused)} refused:",
              file=sys.stderr)
        for r in refused:
            print(f"  - {r}", file=sys.stderr)

    for tool in tools:
        params = [
            inspect.Parameter(n, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=pt)
            for n, pt in tool.params
        ]
        ret = tool.ret_type         

        def _make(descriptor):
            def fn(**kwargs):
                return descriptor.invoke(**kwargs)
            fn.__name__ = descriptor.name
            fn.__doc__ = descriptor.doc
            fn.__signature__ = inspect.Signature(params, return_annotation=ret)
            fn.__annotations__ = {n: pt for n, pt in descriptor.params} | {"return": ret}
            return fn

        mcp.add_tool(_make(tool))
    return mcp


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python -m src.server.mcp_server <lib.so> <spec.yaml>", file=sys.stderr)
        sys.exit(2)
    make_server(sys.argv[1], sys.argv[2]).run()