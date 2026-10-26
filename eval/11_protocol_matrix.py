#!/usr/bin/env python3
"""
Cross-protocol matrix: the same sequences through Python, MCP and gRPC.

    python3 eval/11_protocol_matrix.py --spec snapshots/cjson_audit.yaml --so /tmp/libcjson.so

Adapters (all three call the real generated code, in-process):
  python  src.emit.python.bind_module
  mcp     src.server.mcp_server.make_server -> FastMCP.call_tool (no transport)
  grpc    src.emit.proto.make_servicer -> OpenSession + call (no transport,
          no protobuf serialisation)

Reasons are compared after removing a transport prefix such as
"Error executing tool X: ", surrounding quotes, and handle numbers (gRPC opens a
fresh session per sequence, so its numbering restarts).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys

sys.path.insert(0, ".")

DOC = '{"name":"ferrule","nested":{"n":1}}'
BAD = '{"name": '                      # invalid JSON: cJSON_Parse returns NULL

# (sequence, behaviour it covers, expected final outcome)
SEQUENCES = [
    ("happy_path",          "valid create, use, release",  "accept"),
    ("borrowed_free",       "release of a borrowed handle", "refuse"),
    ("double_free",         "double release",               "refuse"),
    ("stale_after_cascade", "use of an invalidated handle", "refuse"),
    ("null_result",         "call returning NULL",          "accept"),
    ("null_handle",         "NULL passed as a handle",      "accept"),
    ("fabricated_handle",   "handle id never issued",       "refuse"),
]


def norm(reason: str) -> str:
    r = re.sub(r"^Error executing tool \S+:\s*", "", reason or "")
    r = re.sub(r"^\w+(Error|Exception):\s*", "", r)
    r = re.sub(r"\d+", "N", r)          # handle numbers differ per session
    return " ".join(r.strip().strip("'\"").split())


class Outcome:
    def __init__(self, ok: bool, reason: str = "", value=None):
        self.ok, self.reason, self.value = ok, reason, value

    def key(self):
        return (self.ok, norm(self.reason))

    def short(self):
        return ("ACCEPT" if self.ok else "REFUSE") + (f" ({norm(self.reason)[:38]})" if self.reason else "")


def handle_of(v):
    if isinstance(v, dict):
        return v.get("handle")
    if isinstance(v, (tuple, list)) and v and isinstance(v[0], (int, type(None))):
        return v[0]
    return v if isinstance(v, int) else None


class Base:
    name = "?"

    def call(self, fn, **kw) -> Outcome:
        raise NotImplementedError

    def start(self):
        pass

    def run(self, seq) -> Outcome:
        self.start()
        c = self.call
        if seq == "happy_path":
            r = c("cJSON_Parse", value=DOC)
            if not r.ok: return r
            g = c("cJSON_GetObjectItem", handle=handle_of(r.value), string="nested")
            if not g.ok: return g
            return c("cJSON_Delete", handle=handle_of(r.value))
        if seq == "borrowed_free":
            r = c("cJSON_Parse", value=DOC)
            g = c("cJSON_GetObjectItem", handle=handle_of(r.value), string="nested")
            return c("cJSON_Delete", handle=handle_of(g.value))
        if seq == "double_free":
            r = c("cJSON_Parse", value=DOC)
            c("cJSON_Delete", handle=handle_of(r.value))
            return c("cJSON_Delete", handle=handle_of(r.value))
        if seq == "stale_after_cascade":
            r = c("cJSON_Parse", value=DOC)
            g = c("cJSON_GetObjectItem", handle=handle_of(r.value), string="nested")
            c("cJSON_Delete", handle=handle_of(r.value))
            return c("cJSON_GetObjectItem", handle=handle_of(g.value), string="n")
        if seq == "null_result":
            r = c("cJSON_Parse", value=BAD)
            if not r.ok: return r
            return Outcome(True, f"handle={handle_of(r.value)}")
        if seq == "null_handle":
            return c("cJSON_Delete", handle=None)
        if seq == "fabricated_handle":
            return c("cJSON_GetObjectItem", handle=999999, string="x")
        raise KeyError(seq)


class PythonAdapter(Base):
    name = "python"

    def __init__(self, spec, so):
        from src.emit.python import bind_module
        self.m = bind_module(so, spec, name="matrix")

    def call(self, fn, **kw):
        try:
            return Outcome(True, "", getattr(self.m, fn)(**kw))
        except Exception as e:
            return Outcome(False, f"{type(e).__name__}: {e}")


class GrpcAdapter(Base):
    name = "grpc"

    def __init__(self, spec, so):
        from src.emit.proto import make_servicer
        self.s = make_servicer(so, spec)
        self.sid = None

    def start(self):
        self.sid = self.s.OpenSession({})["session_id"]

    def call(self, fn, **kw):
        try:
            return Outcome(True, "", self.s.call(fn, dict(kw, session_id=self.sid)))
        except Exception as e:
            return Outcome(False, f"{type(e).__name__}: {e}")


class McpAdapter(Base):
    name = "mcp"

    def __init__(self, spec, so):
        from src.emit.mcp import make_server
        self.srv = make_server(so, spec)
        tools = asyncio.run(self.srv.list_tools())
        self.names = {t.name.lower(): t.name for t in tools}

    def _parse(self, res):
        if isinstance(res, tuple) and len(res) == 2 and isinstance(res[1], dict):
            v = res[1]
            return v.get("result", v) if set(v) == {"result"} else v
        items = res if isinstance(res, (list, tuple)) else [res]
        texts = [getattr(i, "text", None) for i in items if getattr(i, "text", None) is not None]
        if not texts:
            return None
        try:
            return json.loads(texts[0])
        except (ValueError, TypeError):
            return texts[0]

    def call(self, fn, **kw):
        tool = self.names.get(fn.lower(), fn)
        try:
            v = self._parse(asyncio.run(self.srv.call_tool(tool, kw)))
        except Exception as e:
            return Outcome(False, str(e))
        if isinstance(v, dict) and ("error" in v or "refused" in v):
            return Outcome(False, str(v.get("error") or v.get("refused")), v)
        if isinstance(v, str) and v.upper().startswith(("REFUSED", "ERROR")):
            return Outcome(False, v, v)
        return Outcome(True, "", v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--so", required=True)
    ap.add_argument("--adapters", default="python,mcp,grpc")
    a = ap.parse_args()

    reg = {"python": PythonAdapter, "mcp": McpAdapter, "grpc": GrpcAdapter}
    adapters = []
    for n in a.adapters.split(","):
        try:
            adapters.append(reg[n](a.spec, a.so))
        except Exception as e:
            print(f"!! could not start {n}: {type(e).__name__}: {e}")
    if not adapters:
        return 1

    divergences = 0
    for seq, behaviour, expected in SEQUENCES:
        outs = []
        for ad in adapters:
            try:
                outs.append(ad.run(seq))
            except Exception as e:
                outs.append(Outcome(False, f"HARNESS {type(e).__name__}: {e}"))
        agree = len({o.key() for o in outs}) == 1
        right = all(o.ok == (expected == "accept") for o in outs)
        if not (agree and right):
            divergences += 1
        print(f"\n{seq}  [{behaviour}]  expected {expected.upper()}"
              f"{'' if agree and right else '   <-- DIVERGENCE'}")
        for ad, o in zip(adapters, outs):
            print(f"  {ad.name:7} {o.short()}")
    print(f"\n{len(SEQUENCES)} sequences x {len(adapters)} adapters "
          f"({', '.join(x.name for x in adapters)}): {divergences} divergence(s)")
    return 1 if divergences else 0


if __name__ == "__main__":
    raise SystemExit(main())
