"""
sqlite3's actual deallocator convention is sqlite3DbFree(sqlite3 *db, void *p):
db is the ALLOCATOR CONTEXT (first arg), p is what's actually freed (last arg).

Found via a live sqlite3 infer run: sqlite3_exec, sqlite3_blob_open,
sqlite3_declare_vtab, sqlite3_create_function16, sqlite3_create_collation16,
and sqlite3_table_column_metadata all came back classified `destroys sqlite3`,
which is wrong, none of them close a database connection. The free-detection
loop checked EVERY argument of a dealloc call for a direct struct reference,
so `db` (context, arg 0) got caught alongside the real target.

The fix: only the LAST argument of a dealloc call is the thing being freed.
cJSON's deallocators are single-arg (free(ptr), hooks->deallocate(item)),
where last == only, so this is a strict correctness improvement with no
behavior change there.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.layers.l2_handles import analyze_handles

CONTEXT_ARG_SRC = """typedef unsigned long size_t;
void sqlite3DbFree(void *db, void *p);
typedef struct sqlite3 { int magic; } sqlite3;
typedef struct sqlite3_stmt { int x; } sqlite3_stmt;
sqlite3 *bootstrap_returns_db(sqlite3 *ctx) { return ctx; }
sqlite3_stmt *make_stmt(sqlite3 *db) { sqlite3_stmt *s = 0; return s; }
void sqlite3_exec_like(sqlite3 *db, sqlite3_stmt *stmt) {
    sqlite3DbFree(db, stmt);
}
void free(void *p);
void real_close(sqlite3 *db) { free(db); }
"""

CJSON_SRC = """typedef unsigned long size_t;
void *malloc(size_t);
typedef struct hooks { void *(*allocate)(size_t); void (*deallocate)(void *); } hooks;
hooks global_hooks;
typedef struct node { int v; struct node *child; char *valuestring; } node;
node *new_item(void) { node *n = global_hooks.allocate(sizeof(node)); return n; }
void cjson_delete(node *item) { global_hooks.deallocate(item); }
void set_valuestring(node *object, char *p) { global_hooks.deallocate(object->valuestring); }
"""


def test_context_arg_not_flagged_as_freed():
    """The exact sqlite3DbFree(db, p) pattern: db must NOT be marked destroyed."""
    facts, _ = analyze_handles(CONTEXT_ARG_SRC)
    assert facts["sqlite3_exec_like"].handle_param != "db"

def test_last_arg_is_the_real_free_target():
    facts, _ = analyze_handles(CONTEXT_ARG_SRC)
    assert facts["sqlite3_exec_like"].role == "destroys"
    assert facts["sqlite3_exec_like"].handle_param == "stmt"
    assert facts["sqlite3_exec_like"].handle_type == "sqlite3_stmt"

def test_genuine_single_arg_free_still_works():
    facts, _ = analyze_handles(CONTEXT_ARG_SRC)
    assert facts["real_close"].role == "destroys"
    assert facts["real_close"].handle_param == "db"

def test_cjson_single_arg_member_call_free_unaffected():
    facts, _ = analyze_handles(CJSON_SRC)
    assert facts["cjson_delete"].role == "destroys"
    assert facts["cjson_delete"].handle_param == "item"

def test_cjson_member_access_arg_still_excluded():
    """cJSON_free(object->valuestring) must not flag `object` -- a pre-existing
    fix (direct-reference-only matching) that this change must not undo."""
    facts, _ = analyze_handles(CJSON_SRC)
    assert facts["set_valuestring"].role == "uses"
