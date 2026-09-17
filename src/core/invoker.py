"""
The core invoker -- PROTOCOL-AGNOSTIC.

This is the product. Everything a protocol backend needs is a `Capability`:
neutral input/output field descriptions plus `invoke(**kwargs)` with ctypes
marshalling, handle management and OWNERSHIP ENFORCEMENT already applied.

Protocol emitters (MCP, gRPC, plain Python, ...) are thin adapters over these.
Safety cannot diverge between protocols because there is exactly one enforcement
point -- here and in core/policy.py.

    spec ──► build_capabilities(lib, spec) ──► [Capability, ...]
                                                   │
                            ┌──────────────────────┼──────────────────────┐
                        emit/mcp.py           emit/grpc.py          emit/python.py
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..spec.vocab import Role, Intent
from ..spec.schema import FunctionSpec, LibrarySpec, ParamSpec, ctype_by_name
from .policy import check_exposable, SpecViolation
from .types import CTYPE_TO_PY, py_type_of, py_restype, arg_ctype, to_c, from_c
from .handles import HandleTable, OwnershipError, StaleHandleError
from ..layers.l2_handles import _is_dealloc_name

SCALAR, STRING, ARRAY, HANDLE = "scalar", "string", "array", "handle"


@dataclass
class Field:
    """One neutral input or output field."""
    name: str
    py_type: type
    kind: str = SCALAR
    elem_type: Optional[type] = None
    doc: str = ""


@dataclass
class Capability:
    """A protocol-neutral callable derived from one C function."""
    name: str
    doc: str
    inputs: list[Field]
    outputs: list[Field]
    returns_mapping: bool
    invoke: Callable[..., Any]
    lifecycle: Optional[str] = None
    owner: Optional[str] = None
    handle_type: Optional[str] = None

    @property
    def single_output(self) -> Optional[Field]:
        return self.outputs[0] if len(self.outputs) == 1 and not self.returns_mapping else None


def _bind(lib, fn: FunctionSpec):
    cfn = getattr(lib, fn.name)
    cfn.argtypes = [arg_ctype(p) for p in fn.params]
    cfn.restype = None if fn.restype is None else ctype_by_name(fn.restype)
    if fn.lifecycle in ("creates", "borrows"):
        cfn.restype = ctypes.c_void_p
    elif fn.restype == "c_char_p" and fn.string_owner == "caller":
        cfn.restype = ctypes.c_void_p
    return cfn


def _find_string_deallocator(lib, spec: LibrarySpec):
    '''Find a raw C function to free an OWNED string return (cJSON_Print's
    malloc\'d buffer). This is the one place a WRONG choice is worse than doing
    nothing: calling a struct destructor (cJSON_Delete) on a string buffer is
    memory corruption, not a leak. Disambiguation rule, in order of safety:

      1. name matches the deallocator family (free/dealloc/destroy/...)
      2. takes exactly one parameter (a buffer deallocator is never n-ary)
      3. is NOT already claimed as a struct/handle destructor by handle analysis
         (fn.lifecycle is None) -- this is what rules OUT cJSON_Delete(cJSON*)
         and leaves only cJSON_free(void*).

    If no unambiguous candidate exists, return None: an owned string is then
    left un-freed (the same small, bounded, SAFE leak as before this feature --
    never guess when a wrong guess corrupts the heap).
    '''
    candidates = [
        fn for fn in spec.functions.values()
        if _is_dealloc_name(fn.name) and len(fn.params) == 1 and fn.lifecycle is None
    ]
    if len(candidates) != 1:
        return None
    fn = candidates[0]
    try:
        raw = getattr(lib, fn.name)
        raw.argtypes = [ctypes.c_void_p]
        raw.restype = None
        return raw
    except Exception:
        return None


def _read_and_free_string(addr, dealloc) -> Optional[str]:
    '''Copy a heap-owned C string into Python, then free the C buffer. The
    Python string is an independent copy by the time we free, so this is safe
    regardless of what the client does with the returned str afterward.'''
    if not addr:
        return None
    s = ctypes.string_at(addr).decode(errors="replace")
    if dealloc is not None:
        dealloc(addr)
    return s


def _field_for(p: ParamSpec) -> Field:
    if p.role is Role.HANDLE:
        return Field(p.name, int, HANDLE, doc=f"handle to {p.handle_type or 'object'}")
    if p.role is Role.ARRAY:
        elem = py_type_of(p.ctype)
        return Field(p.name, list, ARRAY, elem_type=elem,
                     doc=f"array of {elem.__name__} (length auto-filled)")
    pt = py_type_of(p.ctype)
    return Field(p.name, pt, STRING if pt is str else SCALAR)


def _out_handle_capability(lib, fn: FunctionSpec, handles: HandleTable) -> Capability:
    """sqlite3_open(path, &db)-shaped: the NEW handle comes out through a T**
    parameter, not the return value -- the return value is typically a status
    code (SQLITE_OK / an error code), which is surfaced alongside the handle.

    This is a distinct calling shape from _lifecycle_capability's "creates"
    (which assumes the return value itself is the handle) and must be checked
    BEFORE it in build_capability's dispatch.
    """
    cfn = getattr(lib, fn.name)
    out_param = next(p for p in fn.params if p.name == fn.handle_out_param)
    in_params = [p for p in fn.params if p.name != fn.handle_out_param]
    cfn.argtypes = [arg_ctype(p) if p.name != fn.handle_out_param
                    else ctypes.POINTER(ctypes.c_void_p) for p in fn.params]
    cfn.restype = None if fn.restype is None else ctype_by_name(fn.restype)

    inputs = [_field_for(p) for p in in_params if p.intent.value is not Intent.OUT]
    outputs = [Field("handle", int, HANDLE, doc=f"handle to {fn.handle_type or 'object'}")]
    if fn.owner != "caller":
        outputs.append(Field("borrowed", bool, SCALAR,
                             doc="ownership not established; this handle cannot be freed"))
    has_status = fn.restype is not None
    if has_status:
        outputs.append(Field("status", py_restype(fn), SCALAR))

    def invoke(**kwargs):
        cell = ctypes.c_void_p()
        args = []
        for p in fn.params:
            if p.name == fn.handle_out_param:
                args.append(ctypes.byref(cell))
            else:
                args.append(to_c(kwargs[p.name], ctype_by_name(p.ctype)))
        ret = cfn(*args)
        result = {}
        if cell.value:
            # owner=caller ONLY when the allocation was actually traced
            # (l2_out_handles confirmed it). A structurally-recognized
            # out-handle carries owner=library, so the caller may USE the handle
            # but the ownership check refuses to free it -- ownership rule 5
            # applied to out-params: unresolved ownership leaks, never
            # double-frees.
            owned = (fn.owner == "caller")
            result["handle"] = handles.put(cell.value, owned=owned)
            if not owned:
                result["borrowed"] = True
        else:
            result["handle"] = None
        if has_status:
            result["status"] = from_c(ret, ctype_by_name(fn.restype))
        return result

    doc = (f"{fn.name}({', '.join(f.name for f in inputs)}) "
          f"[out-param handle:creates {fn.handle_type} owner=caller]")
    return Capability(fn.name, doc, inputs, outputs, True, invoke,
                      fn.lifecycle, fn.owner, fn.handle_type)


def _lifecycle_capability(lib, fn: FunctionSpec, handles: HandleTable,
                          string_dealloc=None) -> Capability:
    """creates / borrows / uses / destroys -- handle-managed.

    SAFETY BUG THIS FIXES: this path never called check_exposable(). A function
    with a lifecycle (e.g. cJSON_PrintPreallocated, lifecycle="uses") skipped the
    fail-safe entirely, because policy was only enforced in the array/plain paths.
    Result: a non-const char* WRITE BUFFER param (role=OPAQUE, meant to be refused)
    was silently bound as a generic int64 in the .proto instead of being rejected.
    Every capability must clear the SAME policy regardless of which builder it
    goes through -- that is the whole point of a shared core.
    """
    check_exposable(fn)
    cfn = _bind(lib, fn)
    hparams = [p for p in fn.params if p.role is Role.HANDLE]
    single = len(hparams) == 1
    hkey = {p.name: ("handle" if single else p.name) for p in hparams}

    inputs = [Field(hkey[p.name], int, HANDLE, doc=f"handle to {fn.handle_type or 'object'}")
              for p in hparams]
    inputs += [_field_for(p) for p in fn.params
               if p.role is not Role.HANDLE and p.intent.value is not Intent.OUT]

    if fn.lifecycle in ("creates", "borrows"):
        outputs = [Field("handle", int, HANDLE, doc=f"handle to {fn.handle_type or 'object'}")]
        if fn.lifecycle == "borrows":
            outputs.append(Field("borrowed", bool, SCALAR,
                                 doc="owned by the library; must not be freed"))
        returns_mapping = True
    elif fn.lifecycle == "destroys":
        outputs = [Field("freed", int, SCALAR),
                   Field("invalidated", list, ARRAY, elem_type=int,
                         doc="handles derived from this one, now invalid"),
                   Field("live_handles", int, SCALAR)]
        returns_mapping = True
    else:
        rt = py_restype(fn)
        outputs = [] if rt is type(None) else [Field("result", rt, STRING if rt is str else SCALAR)]
        returns_mapping = False

    def invoke(**kwargs):
        if fn.lifecycle == "destroys":
            hid = kwargs[hkey[hparams[0].name]]
            if hid is not None and not handles.is_owned(hid):
                raise OwnershipError(
                    f"handle {hid} is BORROWED (owned by the library); freeing it "
                    f"would double-free. Delete its owner instead."
                )
        args = []
        for p in fn.params:
            if p.role is Role.HANDLE:
                hval = kwargs[hkey[p.name]]
                if hval is None:
                    args.append(None)
                else:
                    args.append(handles.get(hval))
            else:
                args.append(to_c(kwargs[p.name], ctype_by_name(p.ctype)))
        ret = cfn(*args)

        if fn.lifecycle in ("creates", "borrows"):
            if not ret:
                return {"handle": None}
            owned = fn.lifecycle == "creates"
            # A borrowed pointer points INTO an object we already hold. Record
            # which one, so destroying that owner invalidates this handle instead
            # of leaving it dangling (the inverse of the double-free check).
            parent = None
            if not owned and hparams:
                parent = kwargs.get(hkey[hparams[0].name])
            hid = handles.put(ret, owned=owned, parent=parent)
            if owned:
                return {"handle": hid}
            return {"handle": hid, "borrowed": True, "parent": parent,
                    "note": "owned by the library; do not free (delete its owner instead)"}
        if fn.lifecycle == "destroys":
            hid = kwargs[hkey[hparams[0].name]]
            if hid is None:
                return {"freed": 0, "invalidated": [], "live_handles": len(handles)}
            _, invalidated = handles.pop_cascade(hid)
            return {"freed": hid, "invalidated": invalidated,
                    "live_handles": len(handles)}
        if fn.restype == "c_char_p" and fn.string_owner == "caller":
            return _read_and_free_string(ret, string_dealloc)
        return from_c(ret, None if fn.restype is None else ctype_by_name(fn.restype))

    own = ""
    if fn.lifecycle == "creates":
        own = " owner=caller"
    elif fn.lifecycle == "borrows":
        own = " owner=library (do not free)"
    doc = f"{fn.name}({', '.join(f.name for f in inputs)}) [handle:{fn.lifecycle} {fn.handle_type}{own}]"
    return Capability(fn.name, doc, inputs, outputs, returns_mapping, invoke,
                      fn.lifecycle, fn.owner, fn.handle_type)


def _array_capability(lib, fn: FunctionSpec) -> Capability:
    """Input array + companion length: caller passes a list, length auto-filled."""
    cfn = _bind(lib, fn)
    length_names = {p.dimension for p in fn.params if p.role is Role.ARRAY}
    arrays = {p.name: p for p in fn.params if p.role is Role.ARRAY}

    inputs = [_field_for(p) for p in fn.params
              if p.name not in length_names and p.intent.value is not Intent.OUT]
    rt = py_restype(fn)
    outputs = [] if rt is type(None) else [Field("result", rt, STRING if rt is str else SCALAR)]

    def invoke(**kwargs):
        built = {}
        for name, p in arrays.items():
            elem = ctype_by_name(p.ctype)
            items = kwargs[name]
            built[name] = (elem * len(items))(*items)
        args = []
        for p in fn.params:
            if p.role is Role.ARRAY:
                args.append(built[p.name])
            elif p.role is Role.LENGTH_OF:
                args.append(len(kwargs[p.dimension]))
            elif p.by_ref:
                base = ctype_by_name(p.ctype)
                args.append(ctypes.byref(base(to_c(kwargs[p.name], base))))
            else:
                args.append(to_c(kwargs[p.name], ctype_by_name(p.ctype)))
        ret = cfn(*args)
        return from_c(ret, None if fn.restype is None else ctype_by_name(fn.restype))

    doc = f"{fn.name}({', '.join(f.name for f in inputs)}) [array; length auto-filled]"
    return Capability(fn.name, doc, inputs, outputs, False, invoke)


def _plain_capability(lib, fn: FunctionSpec, string_dealloc=None) -> Capability:
    """Scalars, strings, and out/inout params (out-params become named outputs)."""
    cfn = _bind(lib, fn)

    inputs = [_field_for(p) for p in fn.params if p.intent.value is not Intent.OUT]
    out_params = [p for p in fn.params if p.by_ref and p.intent.value in (Intent.OUT, Intent.INOUT)]

    rt = py_restype(fn)
    outputs: list[Field] = []
    if rt is not type(None):
        outputs.append(Field("result", rt, STRING if rt is str else SCALAR))
    for p in out_params:
        outputs.append(Field(p.name, py_type_of(p.ctype), SCALAR))
    returns_mapping = bool(out_params)

    def invoke(**kwargs):
        cells, args = {}, []
        for p in fn.params:
            base = ctype_by_name(p.ctype)
            if p.by_ref:
                if p.intent.value is Intent.OUT:
                    cell = base()
                    cells[p.name] = cell
                elif p.intent.value is Intent.INOUT:
                    cell = base(to_c(kwargs[p.name], base))
                    cells[p.name] = cell
                else:
                    cell = base(to_c(kwargs[p.name], base))
                args.append(ctypes.byref(cell))
            else:
                args.append(to_c(kwargs[p.name], base))
        ret = cfn(*args)
        rc = None if fn.restype is None else ctype_by_name(fn.restype)
        if not cells:
            if fn.restype == "c_char_p" and fn.string_owner == "caller":
                return _read_and_free_string(ret, string_dealloc)
            return from_c(ret, rc)
        result = {name: from_c(c.value, ctype_by_name(
            next(p.ctype for p in fn.params if p.name == name))) for name, c in cells.items()}
        if fn.restype is not None:
            result["result"] = from_c(ret, rc)
        return result

    doc = f"{fn.name}({', '.join(f.name for f in inputs)})"
    if out_params:
        doc += f" -> {{{', '.join(f.name for f in outputs)}}}"
    return Capability(fn.name, doc, inputs, outputs, returns_mapping, invoke)


def _caller_state_capability(lib, fn: FunctionSpec, handles: HandleTable) -> Capability:
    """A struct the CALLER allocates and the library only initializes (zlib's
    z_stream). The binding allocates it, so the binding owns it.

    NO STRUCT LAYOUT IS MODELLED. We allocate `state_size` zeroed bytes at
    `state_align` alignment -- both computed by clang for this exact ABI -- hand
    back a handle, and never read or write a field. Every field access is
    performed by the library through its own compiled view of the type, so there
    is no padding, bitfield or packing assumption that could be wrong, because
    there is no assumption at all.

    Ownership needs no inference either: we called the allocator, so we may free
    it. That makes this the one handle kind whose owner is known rather than
    estimated.
    """
    check_exposable(fn)
    cfn = getattr(lib, fn.name)
    cfn.argtypes = [ctypes.c_void_p if p.role is Role.CALLER_STATE else arg_ctype(p)
                    for p in fn.params]
    cfn.restype = None if fn.restype is None else ctype_by_name(fn.restype)

    state_params = [p for p in fn.params if p.role is Role.CALLER_STATE]
    single = len(state_params) == 1
    skey = {p.name: ("state" if single else p.name) for p in state_params}

    inputs = [Field(skey[p.name], int, HANDLE,
                    doc=f"handle to caller-allocated {p.handle_type}")
              for p in state_params]
    inputs += [_field_for(p) for p in fn.params
               if p.role is not Role.CALLER_STATE and p.intent.value is not Intent.OUT]

    rt = py_restype(fn)
    outputs = [] if rt is type(None) else [
        Field("result", rt, STRING if rt is str else SCALAR)]

    def invoke(**kwargs):
        args = []
        for p in fn.params:
            if p.role is Role.CALLER_STATE:
                stored = handles.get(kwargs[skey[p.name]])
                # state handles store (aligned_pointer, backing_buffer) so the
                # buffer stays alive for as long as the handle does
                args.append(stored[0] if isinstance(stored, tuple) else stored)
            else:
                args.append(to_c(kwargs[p.name], ctype_by_name(p.ctype)))
        ret = cfn(*args)
        return from_c(ret, None if fn.restype is None else ctype_by_name(fn.restype))

    doc = (f"{fn.name}({', '.join(f.name for f in inputs)}) "
          f"[caller-allocated {state_params[0].handle_type}]")
    return Capability(fn.name, doc, inputs, outputs, False, invoke,
                      fn.lifecycle, "caller", fn.handle_type)


def make_state_allocator(handles: HandleTable, struct: str, size: int,
                         align: int) -> Capability:
    """Synthetic `alloc_<struct>` capability for caller-allocated state.

    The library has no constructor for this struct -- that is precisely what
    makes it caller-allocated -- so the binding must provide one. Alignment is
    honoured explicitly rather than assumed: a ctypes buffer is not guaranteed
    to satisfy an over-aligned type, so we over-allocate, offset to the required
    boundary, and verify the result.
    """
    def alloc(**_):
        raw = (ctypes.c_char * (size + align))()
        addr = ctypes.addressof(raw)
        aligned = addr + ((-addr) % align)
        if aligned % align:
            raise MemoryError(f"cannot satisfy {align}-byte alignment for {struct}")
        ctypes.memset(aligned, 0, size)
        hid = handles.put((ctypes.c_void_p(aligned), raw), owned=True)
        return {"state": hid, "struct": struct, "bytes": size}

    return Capability(
        f"alloc_{struct}",
        f"Allocate a zeroed, {align}-byte-aligned {struct} ({size} bytes) for the "
        f"library to initialize. The binding owns this memory and may free it.",
        [],
        [Field("state", int, HANDLE, doc=f"handle to a new {struct}"),
         Field("struct", str, STRING),
         Field("bytes", int, SCALAR)],
        True, alloc, "creates", "caller", struct)


def build_capability(lib, fn: FunctionSpec, handles: HandleTable | None = None,
                     string_dealloc=None) -> Capability:
    """One spec function -> one protocol-neutral Capability. Raises SpecViolation
    if policy refuses it.

    The policy check lives HERE, at the single dispatch point, so no calling shape
    can skip it. It previously ran only in the plain/array builders, so anything
    with a handle lifecycle bypassed safety entirely -- that is how
    cJSON_PrintPreallocated's raw `char *buffer` got advertised as an int64
    (an arbitrary-memory-write hole) despite the char* rule being in place.

    `string_dealloc`, if given, is a bound raw C function used to free an OWNED
    string return (see _find_string_deallocator) after it has been copied into
    Python -- resolves cJSON_Print's small per-call leak. Called directly with a
    single function (no `spec`), auto-free is simply unavailable; pass it via
    `build_capabilities` for the library-wide, disambiguated lookup.
    """
    check_exposable(fn)
    if any(p.role is Role.CALLER_STATE for p in fn.params):
        if handles is None:
            raise SpecViolation(f"{fn.name}: caller-state capability needs a handle table")
        return _caller_state_capability(lib, fn, handles)
    if fn.handle_out_param:
        if handles is None:
            raise SpecViolation(f"{fn.name}: out-handle capability needs a handle table")
        return _out_handle_capability(lib, fn, handles)
    if fn.lifecycle in ("creates", "borrows", "uses", "destroys"):
        if handles is None:
            raise SpecViolation(f"{fn.name}: lifecycle capability needs a handle table")
        return _lifecycle_capability(lib, fn, handles, string_dealloc)
    if any(p.role is Role.ARRAY for p in fn.params):
        return _array_capability(lib, fn)
    return _plain_capability(lib, fn, string_dealloc)


def build_capabilities(lib, spec: LibrarySpec, handles: HandleTable | None = None,
                       strict: bool = False):
    """All exposable capabilities. Returns (capabilities, refused[(name, reason)]).

    Refusals are DATA, not failures: a protocol server serves what it can and
    reports the rest (aborting on the first refusal took down whole servers).
    """
    if handles is None:
        handles = HandleTable()
    string_dealloc = _find_string_deallocator(lib, spec)
    caps, refused = [], []

    # One synthetic allocator per caller-allocated struct. Without it the
    # library's init/use/end functions are bindable but uncallable, because
    # nothing can produce the state handle they all take.
    _state_structs: dict = {}
    for _fn in spec.functions.values():
        for _p in _fn.params:
            if _p.role is Role.CALLER_STATE and _p.state_size:
                _state_structs.setdefault(_p.handle_type,
                                          (_p.state_size, _p.state_align or 8))
    for _struct, (_size, _align) in _state_structs.items():
        caps.append(make_state_allocator(handles, _struct, _size, _align))

    for fn in spec.functions.values():
        try:
            caps.append(build_capability(lib, fn, handles, string_dealloc))
        except SpecViolation as e:
            if strict:
                raise
            refused.append((fn.name, str(e).split(";")[0]))
        except AttributeError as e:
            if strict:
                raise
            refused.append((fn.name, f"symbol not found in the .so (platform-specific "
                                     f"or build-config-gated declaration): {e}"))
        except Exception as e:
            if strict:
                raise
            refused.append((fn.name, f"{type(e).__name__}: {e}"))
    return caps, refused