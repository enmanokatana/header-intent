"""
HAND-TRANSLATED reuse of ONE real cJSON test, as a feasibility proof for the
"reuse the library's own test suite as an oracle" methodology (paper section 5).

Source test (cJSON tests/misc_tests.c, NULL-argument subset of
cjson_functions_shouldnt_crash_with_null_pointers):

    TEST_ASSERT_NULL(cJSON_SetValuestring(NULL, "test"));
    TEST_ASSERT_NULL(cJSON_GetObjectItem(NULL, "test"));
    TEST_ASSERT_NULL(cJSON_GetArrayItem(NULL, 0));
    TEST_ASSERT_FALSE(cJSON_HasObjectItem(NULL, "test"));

Every assertion is BLACK-BOX: it checks only the RETURN VALUE, never a struct
field. That is exactly the subset we argue is mechanically reusable. Each C
assertion is translated to the equivalent call against Ferrule's plain-Python
binding, using the SAME literal inputs and expected results cJSON's own
maintainers wrote.

This also answers our open design question empirically: can the binding express
"deliberately pass NULL as a handle argument"? We run it and report rather than
assume.

IMPORTANT: argument names are DISCOVERED from each capability's own signature
docstring, not hard-coded -- the binding may name a handle param "object",
"item", or (from an unnamed header) "a0", and guessing wrong would look like a
binding bug when it is only a wrong guess. We bind by POSITION after discovering
the real names.

Run from your repo root, after building libcjson.so and generating cjson.spec.yaml:
    python3 reuse_cjson_test_manual.py /tmp/cjson/libcjson.so cjson.spec.yaml
"""
import re
import sys


def discover_argnames(fn):
    """Parse the capability's signature out of its __doc__:
       'cJSON_GetObjectItem(object, string) [handle:uses cJSON]' -> ['object','string']"""
    doc = getattr(fn, "__doc__", "") or ""
    m = re.match(r"\s*\w+\(([^)]*)\)", doc)
    if not m:
        return None
    return [a.strip() for a in m.group(1).split(",") if a.strip()]


def call_positional(fn, *values):
    """Call the binding using its REAL argument names, mapped by position to the
    values the C test passed. Returns (ok, result_or_exc)."""
    names = discover_argnames(fn)
    if names is None:
        return False, RuntimeError("could not parse signature from docstring")
    if len(values) != len(names):
        return False, RuntimeError(
            f"arity mismatch: test passes {len(values)} args, "
            f"binding expects {len(names)} {names}")
    kwargs = dict(zip(names, values))
    try:
        return True, fn(**kwargs)
    except Exception as e:
        return False, e


def is_null_result(r):
    if r is None:
        return True
    if isinstance(r, dict):
        if "handle" in r:
            return r["handle"] is None
        if "result" in r:
            return r["result"] in (None, 0)
    return False


def scalar_result(r):
    if isinstance(r, dict):
        for k in ("result", "value", "handle"):
            if k in r:
                return r[k]
    return r


class Report:
    def __init__(self):
        self.p = self.f = self.e = self.skip = 0

    def null(self, label, fn, *values):
        if fn is None:
            print(f"  SKIP  {label}  (function not exposed by binding)")
            self.skip += 1
            return
        ok, r = call_positional(fn, *values)
        if not ok:
            print(f"  ERROR {label}  ({type(r).__name__}: {r})")
            self.e += 1
        elif is_null_result(r):
            print(f"  PASS  {label}")
            self.p += 1
        else:
            print(f"  FAIL  {label}  (expected NULL-equiv, got {r!r})")
            self.f += 1

    def false(self, label, fn, *values):
        if fn is None:
            print(f"  SKIP  {label}  (function not exposed by binding)")
            self.skip += 1
            return
        ok, r = call_positional(fn, *values)
        if not ok:
            print(f"  ERROR {label}  ({type(r).__name__}: {r})")
            self.e += 1
        else:
            v = scalar_result(r)
            if v in (0, False):
                print(f"  PASS  {label}")
                self.p += 1
            else:
                print(f"  FAIL  {label}  (expected FALSE-equiv, got {r!r})")
                self.f += 1


def main():
    if len(sys.argv) != 3:
        print("usage: python3 reuse_cjson_test_manual.py <libcjson.so> <cjson.spec.yaml>")
        sys.exit(2)
    so_path, spec_path = sys.argv[1], sys.argv[2]

    from src.emit.python import bind_module
    m = bind_module(so_path, spec_path)

    exposed = [c for c in dir(m) if c.startswith("cJSON_")]
    print(f"binding exposes {len(exposed)} cJSON_* functions, "
          f"refused {len(m._refused)}\n")

    def get(name):
        f = getattr(m, name, None)
        if f is None:
            reason = ""
            try:
                reason = m._refused.get(name, "")
            except Exception:
                pass
            print(f"  (note: {name} not exposed{': ' + reason if reason else ''})")
        return f

    print("=== reused: cjson_functions_shouldnt_crash_with_null_pointers "
          "(NULL-arg subset) ===")
    print("    (argument names discovered from each binding signature, "
          "values from the C test)\n")

    r = Report()
    # C: TEST_ASSERT_NULL(cJSON_SetValuestring(NULL, "test"));
    r.null('cJSON_SetValuestring(NULL, "test") == NULL',
           get("cJSON_SetValuestring"), None, "test")
    # C: TEST_ASSERT_NULL(cJSON_GetObjectItem(NULL, "test"));
    r.null('cJSON_GetObjectItem(NULL, "test") == NULL',
           get("cJSON_GetObjectItem"), None, "test")
    # C: TEST_ASSERT_NULL(cJSON_GetArrayItem(NULL, 0));
    r.null('cJSON_GetArrayItem(NULL, 0) == NULL',
           get("cJSON_GetArrayItem"), None, 0)
    # C: TEST_ASSERT_FALSE(cJSON_HasObjectItem(NULL, "test"));
    r.false('cJSON_HasObjectItem(NULL, "test") == false',
            get("cJSON_HasObjectItem"), None, "test")

    print(f"\nRESULT: {r.p} passed, {r.f} failed, {r.e} errored, {r.skip} skipped\n")
    print("Interpretation:")
    print("  PASS  = binding reproduces cJSON's own NULL contract AND can pass a NULL handle")
    print("  ERROR = binding cannot express a NULL handle arg (open question answered NO)")
    print("  FAIL  = binding calls C but marshals the result differently than the test expects")
    print("  SKIP  = function refused by the binding; methodology cannot cover it (report honestly)")


if __name__ == "__main__":
    main()
