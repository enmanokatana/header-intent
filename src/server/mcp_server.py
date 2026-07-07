"""
Thin FastMCP wrapper: load a capability spec, build spec-driven tools, register.

This is the ONLY MCP-coupled file; all the logic lives in build.py and is
testable without the `mcp` package. On a machine with `mcp` installed:

    python -m ferrule.server.mcp_server  <lib.so>  <spec.yaml>
"""
import ctypes
import inspect
import sys

from ..spec.io import load_yaml
from ..verify.probes import apply_verification
from .build import build_tools


def make_server(so_path: str, spec_path: str, name: str = "ferrule"):
    from mcp.server.fastmcp import FastMCP     # imported lazily so tests don't need it

    lib = ctypes.CDLL(so_path)
    spec = load_yaml(spec_path)
    apply_verification(lib, spec)              # promote inferred facts before exposing

    mcp = FastMCP(name)
    for tool in build_tools(lib, spec):
        params = [
            inspect.Parameter(n, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=pt)
            for n, pt in tool.params
        ]
        ret = dict if tool.returns_dict else (params[0].annotation if params else type(None))

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
        print("usage: python -m ferrule.server.mcp_server <lib.so> <spec.yaml>", file=sys.stderr)
        sys.exit(2)
    make_server(sys.argv[1], sys.argv[2]).run()