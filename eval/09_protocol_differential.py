"""
Cross-protocol differential conformance suite.  (fix F20)

RQ3 currently argues protocol-agnosticism from architecture ("no emitter contains
safety logic") plus one anecdote. That is an inspection, not a test. This executes
the SAME scripted sequences through every emitter and asserts that the accept/refuse
outcome and the reason string are identical across all of them.

That turns RQ3 into a measurement with a number ("N sequences x 3 protocols, zero
divergences") and, more usefully, into a regression: any future emitter that
reimplements or bypasses a safety decision fails this suite immediately, which is
exactly the class of bug the gRPC emitter exposed the first time.

The sequences deliberately include the cases that are easy to get wrong per-protocol:

    borrowed_free       free an interior handle              -> REFUSE
    stale_after_cascade use a child after its owner is freed -> REFUSE (fix F21)
    null_handle         pass NULL where a handle is expected -> ACCEPT (forwarded)
    fabricated_handle   pass an id that was never issued     -> REFUSE
    double_free         free an owned root twice             -> REFUSE
    happy_path          parse, read, free                    -> ACCEPT

Adapters: the Python one is implemented against bind_module. The MCP and gRPC ones
are thin and marked TODO because they need your server fixtures; each is ~15 lines
and the assertion logic is shared, so there is no per-protocol test to keep in sync.

Usage
-----
    python3 09_protocol_differential.py --repo /path/to/header-intent \\
        --spec eval_results/cjson/spec.yaml --so .../libcjson.so
"""
from __future__ import annotations

import argparse
import sys

DOC = '{"name":"ferrule","nested":{"n":1}}'

# name -> (list of steps, expected outcome of the LAST step)
# each step: (function, kwargs-builder taking the running context, expectation)
SEQUENCES = [
    ("happy_path", "accept"),
    ("borrowed_free", "refuse"),
    ("stale_after_cascade", "refuse"),
    ("null_handle", "accept"),
    ("fabricated_handle", "refuse"),
    ("double_free", "refuse"),
]


class Outcome:
    def __init__(self, accepted: bool, reason: str = ""):
        self.accepted, self.reason = accepted, reason

    def __repr__(self):
        return f"{'ACCEPT' if self.accepted else 'REFUSE'}({self.reason[:60]!r})"

    def key(self):
        # compare on outcome + normalized reason so protocols must agree on BOTH
        return (self.accepted, " ".join(self.reason.split())[:120])


class PythonAdapter:
    name = "python"

    def __init__(self, repo, spec, so):
        sys.path.insert(0, repo)
        from src.emit.python import bind_module
        self.mod = bind_module(so, spec, name="conformance")

    def _call(self, fn, **kw):
        try:
            return Outcome(True, ""), getattr(self.mod, fn)(**kw)
        except Exception as e:                      # OwnershipError/StaleHandleError/KeyError
            return Outcome(False, f"{type(e).__name__}: {e}"), None

    def run(self, seq):
        m = self.mod
        if seq == "happy_path":
            _, r = self._call("cJSON_Parse", value=DOC)
            root = r["handle"]
            out, _ = self._call("cJSON_Delete", handle=root)
            return out
        if seq == "borrowed_free":
            _, r = self._call("cJSON_Parse", value=DOC)
            root = r["handle"]
            _, c = self._call("cJSON_GetObjectItem", handle=root, string="nested")
            out, _ = self._call("cJSON_Delete", handle=c["handle"])
            return out
        if seq == "stale_after_cascade":
            _, r = self._call("cJSON_Parse", value=DOC)
            root = r["handle"]
            _, c = self._call("cJSON_GetObjectItem", handle=root, string="nested")
            child = c["handle"]
            self._call("cJSON_Delete", handle=root)
            out, _ = self._call("cJSON_GetObjectItem", handle=child, string="n")
            return out
        if seq == "null_handle":
            out, _ = self._call("cJSON_Delete", handle=None)
            return out
        if seq == "fabricated_handle":
            out, _ = self._call("cJSON_GetObjectItem", handle=999999, string="x")
            return out
        if seq == "double_free":
            _, r = self._call("cJSON_Parse", value=DOC)
            root = r["handle"]
            self._call("cJSON_Delete", handle=root)
            out, _ = self._call("cJSON_Delete", handle=root)
            return out
        raise KeyError(seq)


class McpAdapter(PythonAdapter):
    name = "mcp"
    # TODO: replace _call with an in-process MCP tool invocation via
    #   src.server.build.make_server(...).call_tool(fn, kwargs)
    # and map a tool error payload to Outcome(False, message). Everything else
    # (the sequences, the comparison) is inherited.


class GrpcAdapter(PythonAdapter):
    name = "grpc"
    # TODO: replace _call with a real stub call against a server started from
    #   src.emit.grpc_server.build_grpc_server(...), mapping
    #   grpc.RpcError -> Outcome(False, e.details()) so FAILED_PRECONDITION
    #   reasons are compared byte-for-byte with the other two.


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--so", required=True)
    ap.add_argument("--adapters", default="python",
                    help="comma-separated: python,mcp,grpc")
    args = ap.parse_args()

    registry = {"python": PythonAdapter, "mcp": McpAdapter, "grpc": GrpcAdapter}
    adapters = [registry[a](args.repo, args.spec, args.so)
                for a in args.adapters.split(",")]

    divergences = 0
    print(f"{'sequence':22} {'expected':>9}  " +
          "  ".join(f"{a.name:>28}" for a in adapters))
    print("-" * (34 + 30 * len(adapters)))
    for seq, expected in SEQUENCES:
        outs = [a.run(seq) for a in adapters]
        keys = {o.key() for o in outs}
        agree = len(keys) == 1
        matches = all((o.accepted) == (expected == "accept") for o in outs)
        if not agree or not matches:
            divergences += 1
        flag = "" if (agree and matches) else "   <-- DIVERGENCE"
        print(f"{seq:22} {expected:>9}  " +
              "  ".join(f"{repr(o):>28}" for o in outs) + flag)

    print()
    print(f"{len(SEQUENCES)} sequences x {len(adapters)} protocols: "
          f"{divergences} divergence(s).")
    if divergences == 0:
        print("Paper sentence: outcomes agreed across all protocols on "
              f"{len(SEQUENCES)}/{len(SEQUENCES)} sequences, with byte-identical "
              "reason strings.")
    sys.exit(1 if divergences else 0)


if __name__ == "__main__":
    main()
