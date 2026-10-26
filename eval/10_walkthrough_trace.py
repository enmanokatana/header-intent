#!/usr/bin/env python3
"""
Run Example 1 through the real cJSON binding and print, after each step, the
call's result and the handle table's state.

    python3 eval/10_walkthrough_trace.py /tmp/libcjson.so snapshots/cjson_audit.yaml
"""
import re
import sys

sys.path.insert(0, ".")
from src.emit.python import bind_module

so, spec = sys.argv[1], sys.argv[2]
m = bind_module(so, spec, name="trace")
t = m._handles


def params(f):
    mt = re.match(r"\s*[\w.]+\((.*?)\)", f.__doc__ or "")
    return [p.strip() for p in mt.group(1).split(",") if p.strip()] if mt else []


def call(name, *args):
    f = getattr(m, name)
    kw = dict(zip(params(f), args))
    try:
        r = f(**kw)
    except Exception as e:
        r = f"{type(e).__name__}: {e}"
    print(f"\n{name}({', '.join(f'{k}={v!r}' for k, v in kw.items())})")
    print(f"  result : {r}")
    return r


def table(*hids):
    for h in hids:
        if h is None:
            continue
        live = t.is_live(h)
        line = f"  handle {h}: live={live}"
        if live:
            line += f" owned={t.is_owned(h)} parent={t.parent_of(h)} children={sorted(t.children_of(h))}"
        elif h in getattr(t, "_invalidated", {}):
            line += f" invalidated by owner {t._invalidated[h]}"
        print(line)


for n in ("cJSON_Parse", "cJSON_GetObjectItem", "cJSON_Delete"):
    print(f"{n}: {getattr(m, n).__doc__}")

r = call("cJSON_Parse", '{"a": {"b": 1}}')
root = r["handle"] if isinstance(r, dict) else r
table(root)

r = call("cJSON_GetObjectItem", root, "a")
child = r["handle"] if isinstance(r, dict) else r
table(root, child)

call("cJSON_Delete", child)          # borrowed: expect a refusal before the C call
table(root, child)

call("cJSON_Delete", root)           # owned: expect freed + child invalidated
table(root, child)

call("cJSON_GetObjectItem", child, "b")   # dangling borrowed handle: expect a refusal
