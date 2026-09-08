"""
Handle-lifecycle (creates/uses/destroys) classification had NO forwarding
resolution at all -- unlike ownership inference (fixed-point over the call
graph) and out-param-handle confirmation (one-hop forward), it only checked
whether a function's OWN body directly calls a deallocator.

Found via a live MCP server: sqlite3_close returned {"result": 0} instead of
{"freed": ..., "live_handles": ...} -- meaning it was bound as a "uses" tool,
never popping the handle from our HandleTable, even though the underlying C
call genuinely closed and freed the connection. Reusing that handle afterward
would hand an already-freed C pointer straight into a library call: the
INVERSE of the double-free protection this whole ownership system exists to
provide, and arguably worse, since nothing about it looks unsafe until the
freed memory is actually touched.

Root cause: sqlite3_close forwards through TWO hops before the real free:
    sqlite3_close(db) -> sqlite3Close(db, 0)
    sqlite3Close(db, fz) -> ... six other helper calls ... -> sqlite3LeaveMutexAndCloseZombie(db)
    sqlite3LeaveMutexAndCloseZombie(db) -> ... -> sqlite3_free(db)

The fix: a fixed-point pass over ALL direct-argument callees of a handle
param (there can be several -- the middle hop passes `db` to six different
helpers, only one of which is the real closer), promoting to "destroys" when
any of them resolves, via the same fixed point, to "destroys" at the matching
parameter position.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ferrule.layers.l2_handles import analyze_handles

# faithful reproduction of the real sqlite3_close chain, including the
# "many callees receive db directly, only one actually frees it" complexity
TWO_HOP_SRC = r"""
typedef unsigned long size_t;
void free(void *p);
typedef struct sqlite3 { int mutex; } sqlite3;
sqlite3 *bootstrap_returns_db(sqlite3 *ctx) { return ctx; }
int sqlite3SafetyCheckSickOrOk(sqlite3 *db) { return 1; }
void disconnectAllVtab(sqlite3 *db) { }
void sqlite3VtabRollback(sqlite3 *db) { }
int connectionIsBusy(sqlite3 *db) { return 0; }
void sqlite3ErrorWithMsg(sqlite3 *db, int rc, const char *msg) { }
void sqlite3LeaveMutexAndCloseZombie(sqlite3 *db) {
    free(db);
}
int sqlite3Close(sqlite3 *db, int forceZombie) {
    if (!sqlite3SafetyCheckSickOrOk(db)) { return 1; }
    if (connectionIsBusy(db)) {
        sqlite3ErrorWithMsg(db, 5, "busy");
        return 5;
    }
    disconnectAllVtab(db);
    sqlite3VtabRollback(db);
    sqlite3LeaveMutexAndCloseZombie(db);
    return 0;
}
int sqlite3_close(sqlite3 *db) {
    return sqlite3Close(db, 0);
}
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


def test_two_hop_chain_resolves_to_destroys():
    """THE bug: sqlite3_close, two hops removed from the real free, must
    still classify as destroys."""
    facts, _ = analyze_handles(TWO_HOP_SRC)
    assert facts["sqlite3_close"].role == "destroys"
    assert facts["sqlite3_close"].handle_param == "db"

def test_middle_hop_resolves_too():
    """sqlite3Close itself (one hop from the real free) must also resolve,
    since it's what sqlite3_close forwards through."""
    facts, _ = analyze_handles(TWO_HOP_SRC)
    assert facts["sqlite3Close"].role == "destroys"
    assert facts["sqlite3Close"].handle_param == "db"

def test_unrelated_helpers_among_many_callees_stay_uses():
    """sqlite3Close passes `db` directly to SIX different helpers; only the
    one that genuinely leads to a free must be promoted. The other five
    (validation/cleanup helpers that never free anything) must NOT be
    falsely promoted just because they also receive db directly."""
    facts, _ = analyze_handles(TWO_HOP_SRC)
    for name in ("sqlite3SafetyCheckSickOrOk", "disconnectAllVtab",
                 "sqlite3VtabRollback", "connectionIsBusy"):
        assert facts[name].role == "uses", f"{name} must not be falsely promoted"

def test_the_real_closer_is_destroys():
    facts, _ = analyze_handles(TWO_HOP_SRC)
    assert facts["sqlite3LeaveMutexAndCloseZombie"].role == "destroys"

def test_cjson_direct_single_hop_free_unaffected():
    """The new forwarding pass must not change behavior for the direct case
    that already worked (cJSON's actual convention)."""
    facts, _ = analyze_handles(CJSON_SRC)
    assert facts["cjson_delete"].role == "destroys"
    assert facts["cjson_delete"].handle_param == "item"

def test_cjson_member_access_still_excluded():
    facts, _ = analyze_handles(CJSON_SRC)
    assert facts["set_valuestring"].role == "uses"


def test_cross_type_free_does_not_promote_destroys():
    """Real libpq case: PQexec(PGconn *conn) calls pqClearAsyncResult(conn),
    which frees conn->result (a PGresult MEMBER), not conn. The callee is a
    PGresult destructor; forwarding must NOT promote PQexec to destroys-PGconn,
    because that would free the live connection after one query (use-after-free).
    The type-match guard rejects the cross-type promotion."""
    src = '''
    typedef struct PGresult { int x; } PGresult;
    typedef struct PGconn { PGresult *result; } PGconn;
    void free(void *p);
    PGconn *PQconnectbootstrap(void) { PGconn *c = 0; return c; }
    PGresult *PQmakeResult(PGconn *conn) { PGresult *r = 0; return r; }
    void PQclear(PGresult *res) { free(res); }
    void pqClearAsyncResult(PGconn *conn) { PQclear(conn->result); }
    void PQexec(PGconn *conn) { pqClearAsyncResult(conn); }
    void realClose(PGconn *conn) { free(conn); }
    '''
    facts, _ = analyze_handles(src)
    # PQclear genuinely destroys a PGresult
    assert facts["PQclear"].role == "destroys"
    assert facts["PQclear"].handle_type == "PGresult"
    # pqClearAsyncResult frees conn->result (member), NOT conn -> must NOT be destroys-PGconn
    assert facts.get("pqClearAsyncResult") is None or \
           facts["pqClearAsyncResult"].role != "destroys" or \
           facts["pqClearAsyncResult"].handle_type != "PGconn"
    # PQexec must NOT be promoted to destroys-PGconn via cross-type forwarding
    assert facts.get("PQexec") is None or \
           facts["PQexec"].role != "destroys" or \
           facts["PQexec"].handle_type != "PGconn", \
           "PQexec must not be a PGconn destructor -- it only frees a PGresult member"
    # a genuine same-type destructor still works
    assert facts["realClose"].role == "destroys"
    assert facts["realClose"].handle_type == "PGconn"