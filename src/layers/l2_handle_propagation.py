"""
L2 coverage extensions: recover bindable contracts the role vocabulary could
previously not EXPRESS.

MOTIVATION
----------
An audit of the refusal set across six libraries showed that `opaque` refusals
are dominated not by genuinely unbindable idioms (callbacks, writable buffers)
but by HANDLE PARAMETERS THE ANALYSIS FAILED TO CONNECT:

    libgit2   226x 'out', 78x 'repo', 28x 'index', 20x 'remote'
    libpq      81x 'conn', 30x 'res'
    libpng    202x 'png_ptr'
    zlib       28x 'strm', 21x 'file'

`PGconn*`, `png_struct*` and `git_repository*` are handle types the library
hands out and manages. They were refused because L0 discards the pointee type
name for `T*` parameters (everything degrades to `c_void_p`), so nothing
downstream could tell a handle from an arbitrary pointer.

THE SAFETY LINE
---------------
There are two ways to raise coverage, and only one of them is legitimate here:

  LEGITIMATE   extend the VOCABULARY so a contract that was always true becomes
               EXPRESSIBLE. The gate is unchanged; a function becomes bindable
               because its contract is now known, not because the bar dropped.

  DANGEROUS    relax check_exposable so unestablished contracts pass anyway.
               That destroys the abstention property the whole design rests on.

Every pass in this module is the first kind, and each one states below why it
grants no permission the runtime did not already enforce.

THREE PASSES
------------
1. propagate_handle_types  -- a `T*` param where T is a type the library hands
   out is a HANDLE. Grants nothing: handle ids are opaque integers the caller
   can only have obtained from a previous call, the handle table still checks
   ownership before any free, and a fabricated id still raises.

2. promote_structural_out_handles -- a `T**` param where T is a known handle
   type is an out-handle even when the body-level allocation trace failed.
   CRITICALLY: unconfirmed ones are marked owner=library (BORROWED), so the
   caller can use the handle but can never free it. This is exactly rule 5 of
   the ownership fail-safe: unresolved ownership degrades to a leak, never to a
   double free.

3. detect_caller_allocated_state -- a struct the CALLER allocates and the
   library only initializes (zlib's z_stream). The binding allocates a
   correctly-sized, correctly-aligned, zeroed buffer and never reads a field of
   it. No struct layout is modelled, so no layout can be got wrong: clang
   reports the exact size and alignment for the target ABI, and every field
   access stays inside the library.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..spec.vocab import Role, Intent
from ..spec.schema import Evidenced


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_COUNT_WORDS = {"n", "num", "count", "cnt", "len", "length", "size",
                "nmemb", "nitems", "total"}
_COUNT_PREFIX = re.compile(r"^(num|cnt|len)", re.I)


def _looks_like_count(name: str) -> bool:
    """True if this identifier plausibly names an element count.

    Word-level, so `bit_depth` (bits per sample) does not fire while
    `num_palette`, `numAttributes` and `nmemb` do. Uses the ownership layer's
    tokenizer instead of a local copy: a boundary regex tuned on snake_case
    missed camelCase here exactly as it once hid sqlite3MallocZero from the
    allocator matcher, and one shared tokenizer is what stops that recurring.

    Known conservative false positive: `good_length` in deflateTune fires on
    `length`, so deflateTune is refused as taking an array. Known gap: a bare
    `nentries` tokenizes to one word and is not recognised.
    """
    from .l2_ownership import _tokenize_ident
    toks = _tokenize_ident(name or "")
    return (any(t in _COUNT_WORDS for t in toks)
            or any(_COUNT_PREFIX.match(t) for t in toks))


def _adjacent_count_param(fn, idx: int):
    """Name of an element-count parameter immediately BEFORE or AFTER index
    `idx`, or None. Truthy either way; returns the name so the refusal note
    can say which parameter is the evidence.

    Both call sites are memory-safety guards. In pass 1 a missed array lets
    the caller pass one object's address as a handle while the library reads
    n of them -- an out-of-bounds read. In pass 3 the binding allocates one
    struct where the library indexes an array --
        png_set_PLTE(png, info, png_color *palette, int num_palette)
    would overflow a single 3-byte allocation.

    Both sides, because counts come first about as often as last:
        PQsetResultAttrs(PGresult *res, int numAttributes, PGresAttDesc *attDescs)
    """
    for j in (idx + 1, idx - 1):
        if j < 0 or j >= len(fn.params):
            continue
        nb = fn.params[j]
        if nb.role not in (Role.SCALAR, Role.LENGTH_OF):
            continue
        if _looks_like_count(nb.name):
            return nb.name
    return None


# ---------------------------------------------------------------------------
# Pass 1: propagate handle types to every function that touches them
# ---------------------------------------------------------------------------

def propagate_handle_types(spec, handle_types: set, pointees: dict) -> list[str]:
    """Mark every `T*` parameter as a HANDLE when T is a type this library hands
    out, regardless of whether that function received a lifecycle verdict.

    `apply_handle_facts` only marks parameters on functions the source analysis
    actually classified. A function whose definition was not parsed, or that got
    no create/use/destroy verdict, keeps its `T*` parameter as OPAQUE even when
    the library unambiguously manages T elsewhere. libpq's 81 `conn` refusals
    are exactly this: PQconnectdb establishes that `PGconn` is a handle type,
    and every other function taking `PGconn*` should inherit that.

    `pointees` is {function: {param: struct_name}} recovered by L0 (see
    extract._struct_ptr_param).

    WHY THIS GRANTS NO NEW PERMISSION
    ---------------------------------
    A HANDLE parameter is marshalled as an opaque integer id. The caller cannot
    fabricate one: HandleTable.get raises for any id it did not issue, and
    raises StaleHandleError for one invalidated by its owner's destruction. The
    ownership check still runs before any destroy. All this pass changes is that
    a pointer the runtime was ALREADY prepared to manage safely can now be
    named in a signature instead of refused.
    """
    notes = []
    for fname, fn in spec.functions.items():
        fn_pointees = pointees.get(fname, {})
        if not fn_pointees:
            continue
        for idx, p in enumerate(fn.params):
            if p.role is not Role.OPAQUE:
                continue
            struct = fn_pointees.get(p.name)
            if struct is None or struct not in handle_types:
                continue
            count_param = _adjacent_count_param(fn, idx)
            if count_param:
                notes.append(f"{fname}: {p.name!r} is {struct}* but is followed by a "
                             f"count parameter ({count_param!r}); treated as a "
                             f"potential array, left refused")
                continue
            p.role = Role.HANDLE
            p.handle_type = struct
            p.intent = Evidenced(Intent.IN, ["handle_propagation"], 0.8, verified=False)
            notes.append(f"{fname}: {p.name!r} -> HANDLE {struct} (type is handed out "
                         f"by this library)")
            if fn.handle_type is None:
                fn.handle_type = struct
            if fn.lifecycle is None:
                # It touches a handle but we have no create/destroy evidence.
                # "uses" is the correct conservative verdict: it grants no
                # release, so a missed destructor leaks rather than releasing a
                # live handle.
                fn.lifecycle = "uses"
    return notes


# ---------------------------------------------------------------------------
# Pass 2: structural out-handle recognition, borrowed by default
# ---------------------------------------------------------------------------

def promote_structural_out_handles(spec, handle_types: set, candidates: dict,
                                   confirmed: set) -> list[str]:
    """Accept a `T**` parameter as an out-handle on STRUCTURAL evidence when T is
    a known handle type, even if the body-level allocation trace failed.

    l2_out_handles confirms a candidate only when it can trace `*out = <alloc>`
    or a single clean forward to a callee that can. libgit2 writes to `out`
    several helper calls deep, through branches the tracer will not follow, so
    226 of its parameters fall back to OPAQUE and the function is refused --
    including git_repository_open, the entry point to the whole API.

    OWNERSHIP IS THE POINT
    ----------------------
    A confirmed out-handle is owner=caller: we watched an allocation flow into
    it. A merely structural one is owner=LIBRARY, i.e. borrowed:

        confirmed  -> caller owns  -> may be freed through its destructor
        structural -> library owns -> handle is usable, freeing is REFUSED

    That is ownership rule 5 applied unchanged: where the analysis cannot
    establish ownership it assumes the library keeps it, so a wrong guess leaks
    memory instead of double-freeing it. The caller gets a usable handle for
    every call in the API and loses only the ability to release it, which is
    the strictly safer half of the contract.
    """
    notes = []
    for fname, fn in spec.functions.items():
        fn_cands = candidates.get(fname, {})
        if not fn_cands:
            continue
        if fn.handle_out_param:
            continue                      # already confirmed by l2_out_handles
        for p in fn.params:
            if p.role is not Role.OUT_HANDLE and p.role is not Role.OPAQUE:
                continue
            struct = fn_cands.get(p.name)
            if struct is None or struct not in handle_types:
                continue
            if (fname, p.name) in confirmed:
                continue
            p.role = Role.OUT_HANDLE
            p.handle_type = struct
            p.intent = Evidenced(Intent.OUT, ["structural_out_handle"], 0.7,
                                 verified=False)
            fn.handle_out_param = p.name
            fn.handle_type = struct
            fn.lifecycle = "creates"
            fn.owner = "library"          # <-- borrowed: usable, never freeable
            notes.append(f"{fname}: {p.name!r} -> OUT_HANDLE {struct} (structural; "
                         f"allocation not traced, so owner=library and the handle "
                         f"cannot be freed through this binding)")
            break
    return notes


# ---------------------------------------------------------------------------
# Pass 3: caller-allocated state
# ---------------------------------------------------------------------------

@dataclass
class CallerStateFact:
    struct: str
    size: int
    align: int
    init_fn: str | None = None
    end_fn: str | None = None
    evidence: list = field(default_factory=list)


_INIT_HINT = re.compile(r"(init|begin|start|setup|open)", re.I)
_END_HINT = re.compile(r"(end|close|finish|cleanup)", re.I)
# Deliberately NARROWER than _END_HINT: these words mean "this function releases
# the object", whereas "end"/"finish" often mean "release what the object holds"
# (zlib's deflateEnd frees the stream's internal buffers, not the z_stream).
_FREE_HINT = re.compile(r"(free|destroy|release|dispose|delete|unref)", re.I)


def detect_caller_allocated_state(spec, pointees: dict, struct_sizes: dict,
                                  handle_types: set, out_handle_candidates: dict
                                  ) -> tuple[dict, list[str]]:
    """Find structs the CALLER allocates and the library only initializes.

    zlib's z_stream is the canonical case: the caller declares it, zeroes a few
    fields, and passes its address to deflateInit2_. The library never returns
    one and never frees one, so handle-lifecycle analysis correctly produces no
    verdict -- and the binding correctly refuses the entire compression API.

    THIS PASS IS BUILT ON A GUARD THAT CAN GO VACUOUS, SO IT CHECKS FIRST
    ----------------------------------------------------------------------
    The original formulation asked "is this struct NEVER returned and NEVER
    freed by the library?" -- inferring caller-ownership from the ABSENCE of
    evidence. On a library where handle analysis produced nothing (a failed
    parse, an unsupported idiom), that question answers "yes" for EVERY struct,
    and the pass claims ownership of the library's own handles. Observed on
    libpng and libgit2: 519 parameters reclassified, including png_struct's
    FILE*, png_color palettes, and git_signature.

    Absence of evidence is not evidence of caller ownership. Every guard below
    therefore demands a positive reason to believe the binding may allocate, and
    the pass disables itself entirely when it cannot trust its own inputs.
    """
    notes = []

    # GUARD 0: if lifecycle analysis found no handle types at all, we cannot
    # distinguish "the library does not manage this struct" from "we failed to
    # see that it does". Refuse the whole pass rather than guess per struct.
    if not handle_types:
        notes.append("caller-state detection skipped: handle analysis produced no "
                     "handle types for this library, so 'not library-managed' "
                     "cannot be distinguished from 'not analyzed' (fail-safe)")
        return {}, notes

    returned = set(handle_types)

    # GUARD 1: a struct handed back through a T** out-parameter is allocated BY
    # the library (git_signature_new, git_repository_open). Those never appear
    # in struct_ptr_params, so the "never returned" test misses them entirely.
    via_out_param = {s for cands in out_handle_candidates.values()
                     for s in cands.values()}

    # GUARD 2: destructors, by lifecycle verdict AND lexically. The lexical half
    # matters because it survives a failed lifecycle analysis: git_signature_free
    # taking git_signature* is sufficient evidence the library owns the type.
    destroyed = {fn.handle_type for fn in spec.functions.values()
                 if fn.lifecycle in ("destroys", "uncertain_destroys") and fn.handle_type}
    for fname, fn_pointees in pointees.items():
        if _FREE_HINT.search(fname):
            destroyed.update(fn_pointees.values())

    taken: dict[str, list[str]] = {}
    for fname, fn_pointees in pointees.items():
        for pname, struct in fn_pointees.items():
            taken.setdefault(struct, []).append(fname)

    facts: dict[str, CallerStateFact] = {}
    for struct, users in taken.items():
        if struct in returned:
            continue                       # library hands it out: a real handle
        if struct in via_out_param:
            notes.append(f"{struct}: written through a T** out-parameter, so the "
                         f"library allocates it; not caller-allocated state")
            continue
        if struct in destroyed:
            notes.append(f"{struct}: the library exposes a destructor for it, so "
                         f"the library owns its lifetime; not caller-allocated state")
            continue

        dims = struct_sizes.get(struct)
        if not dims or dims.get("size", 0) <= 0:
            notes.append(f"{struct}: caller-allocated candidate but no size from "
                         f"clang; left refused (cannot allocate what we cannot size)")
            continue

        # GUARD 3: the struct must be declared by THIS library. A system type
        # (FILE, struct tm, sockaddr) is allocated and owned by libc, and handing
        # the library a zeroed buffer where it expects a live FILE is immediate
        # corruption. L0 records this; a missing flag is treated as foreign.
        if not dims.get("local"):
            notes.append(f"{struct}: not declared by this library (system or "
                         f"third-party type); the binding must never allocate it")
            continue

        # GUARD 4: require an initializer. Caller-allocated state exists to be
        # handed to a function that fills it in; a struct with no such function
        # is more likely an argument record we have simply not understood.
        init_fn = next((f for f in users if _INIT_HINT.search(f)), None)
        if init_fn is None:
            notes.append(f"{struct}: no initializing function found among its "
                         f"{len(users)} users; refused rather than assumed")
            continue

        fact = CallerStateFact(struct, dims["size"], dims.get("align", 8))
        fact.init_fn = init_fn
        fact.end_fn = next((f for f in users if _END_HINT.search(f)), None)
        fact.evidence = [f"{len(users)} functions take {struct}*",
                         "declared by this library",
                         "never returned, never freed, never an out-parameter",
                         f"initialized by {init_fn}",
                         f"size={fact.size} align={fact.align} (clang, target ABI)"]
        facts[struct] = fact
        notes.append(f"{struct}: CALLER_STATE (size={fact.size}, align={fact.align}, "
                     f"init={fact.init_fn}, end={fact.end_fn})")
    return facts, notes


def apply_caller_state_facts(spec, facts: dict, pointees: dict) -> list[str]:
    """Mark every `T*` parameter of a caller-allocated struct as CALLER_STATE.

    The array guard is the same one pass 1 uses, and it matters more here:
    png_set_PLTE(png_ptr, png_color *palette, int num_palette) passes an ARRAY of
    up to 256 entries. Allocating one 3-byte png_color for it and letting the
    library index palette[i] is a buffer overflow, not a coverage gap.
    """
    notes = []
    for fname, fn in spec.functions.items():
        fn_pointees = pointees.get(fname, {})
        for idx, p in enumerate(fn.params):
            if p.role is not Role.OPAQUE:
                continue
            struct = fn_pointees.get(p.name)
            if struct is None or struct not in facts:
                continue
            count_param = _adjacent_count_param(fn, idx)
            if count_param:
                notes.append(f"{fname}: {p.name!r} is {struct}* next to a count "
                             f"parameter ({count_param!r}); this is an "
                             f"array, not a single struct -- left refused")
                continue
            f = facts[struct]
            p.role = Role.CALLER_STATE
            p.handle_type = struct
            p.state_size = f.size
            p.state_align = f.align
            p.intent = Evidenced(Intent.INOUT, ["caller_state"], 0.8, verified=False)
            if fn.handle_type is None:
                fn.handle_type = struct
            notes.append(f"{fname}: {p.name!r} -> CALLER_STATE {struct} "
                         f"({f.size} bytes, binding-allocated)")
    return notes


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def apply_coverage_extensions(spec, *, handle_types: set, pointees: dict,
                              out_handle_candidates: dict, struct_sizes: dict,
                              confirmed_out_handles: set | None = None,
                              enable_caller_state: bool = True) -> list[str]:
    """Run all three passes in dependency order and return the report notes.

    Order matters: propagation must run before caller-state detection, because
    detection asks whether a struct is a library-managed handle, and propagation
    is what establishes the answer for types no single function's verdict
    covered.
    """
    notes: list[str] = []
    notes += propagate_handle_types(spec, handle_types, pointees)
    notes += promote_structural_out_handles(
        spec, handle_types, out_handle_candidates, confirmed_out_handles or set())
    if enable_caller_state:
        facts, fnotes = detect_caller_allocated_state(
            spec, pointees, struct_sizes, handle_types, out_handle_candidates)
        notes += fnotes
        notes += apply_caller_state_facts(spec, facts, pointees)
    return notes