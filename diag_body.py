
from clang import cindex

SRC = "/tmp/cjson/cJSON.c"
ARGS = ["-I", "/tmp/cjson"]

tu = cindex.Index.create().parse(SRC, args=ARGS)

print("=== TU DIAGNOSTICS (errors here can truncate bodies) ===")
errs = list(tu.diagnostics)
if not errs:
    print("  (none)")
for d in errs[:20]:
    print(f"  sev={d.severity} {d.location} :: {d.spelling}")
print()

TARGET = "cJSON_ParseWithOpts"
print(f"=== EVERY cursor named {TARGET} ===")
found = 0
for c in tu.cursor.walk_preorder():
    if c.kind != cindex.CursorKind.FUNCTION_DECL or c.spelling != TARGET:
        continue
    found += 1
    f = c.location.file.name if c.location.file else "?"
    kids = [k.kind.name for k in c.get_children()]
    ntok = len(list(c.get_tokens()))
    print(f"  [{found}] file={f}")
    print(f"       line={c.location.line}  is_definition={c.is_definition()}")
    print(f"       child kinds : {kids}")
    print(f"       token count : {ntok}")
    has_body = any(k == "COMPOUND_STMT" for k in kids)
    print(f"       HAS BODY (COMPOUND_STMT): {has_body}")
    if has_body:
        body = next(k for k in c.get_children()
                    if k.kind == cindex.CursorKind.COMPOUND_STMT)
        stmts = [s.kind.name for s in body.get_children()]
        print(f"       body stmt kinds: {stmts}")
    print()

if found == 0:
    print("  <no cursor found at all>")

print("=== for contrast: cJSON_ParseWithLength (this one works) ===")
for c in tu.cursor.walk_preorder():
    if c.kind == cindex.CursorKind.FUNCTION_DECL and c.spelling == "cJSON_ParseWithLength" \
            and c.is_definition():
        kids = [k.kind.name for k in c.get_children()]
        print(f"  child kinds: {kids}")
        body = [k for k in c.get_children() if k.kind == cindex.CursorKind.COMPOUND_STMT]
        if body:
            print(f"  body stmts : {[s.kind.name for s in body[0].get_children()]}")
        break
