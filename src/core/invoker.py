from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..spec.vocab import Role, Intent
from ..spec.schema import FunctionSpec, LibrarySpec, ParamSpec, ctype_by_name
from .policy import check_exposable, SpecViolation
from .types import CTYPE_TO_PY, py_type_of, py_restype, arg_ctype, to_c, from_c
from .handles import HandleTable, OwnershipError
from ..layers.l2_handles import _is_dealloc_name

SCALAR, STRING, ARRAY, HANDLE = "scalar", "string", "array", "handle"


@dataclass
class Field:
    """One neutral input or output field."""
    name: str
    py_type: type                       # int | float | str | bool | list
    kind: str = SCALAR                  # SCALAR | STRING | ARRAY | HANDLE
    elem_type: Optional[type] = None    # element type when kind == ARRAY
    doc: str = ""


@dataclass
class Capability:
    """A protocol-neutral callable derived from one C function."""
    name: str
    doc: str
    inputs: list[Field]
    outputs: list[Field]                # >1 when there are out-params; [] for void
    returns_mapping: bool               # invoke() returns a dict of named outputs
    invoke: Callable[..., Any]
    # semantic metadata emitters may use (gRPC streaming, docs, ...)
    lifecycle: Optional[str] = None     # creates | borrows | uses | destroys
    owner: Optional[str] = None         # caller | library
    handle_type: Optional[str] = None

    @property
    def single_output(self) -> Optional[Field]:
        return self.outputs[0] if len(self.outputs) == 1 and not self.returns_mapping else None


def _bind(lib, fn: FunctionSpec):
    cfn = getattr(lib, fn.name)
    cfn.argtypes = [arg_ctype(p) for p in fn.params]
    cfn.restype = None if fn.restype is None else ctype_by_name(fn.restype)
    if fn.lifecycle in ("creates", "borrows"):
        cfn.restype = ctypes.c_void_p          # a returned handle is an address
    elif fn.restype == "c_char_p" and fn.string_owner == "caller":
        # an OWNED string: bind as a raw address (not ctypes' auto-copying
        # c_char_p) so we can free the C buffer AFTER copying it ourselves.
        cfn.restype = ctypes.c_void_p
    return cfn


def _find_string_deallocator(lib, spec: LibrarySpec):
    
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
    
    cfn = getattr(lib, fn.name)
    out_param = next(p for p in fn.params if p.name == fn.handle_out_param)
    in_params = [p for p in fn.params if p.name != fn.handle_out_param]
    cfn.argtypes = [arg_ctype(p) if p.name != fn.handle_out_param
                    else ctypes.POINTER(ctypes.c_void_p) for p in fn.params]
    cfn.restype = None if fn.restype is None else ctype_by_name(fn.restype)

    inputs = [_field_for(p) for p in in_params if p.intent.value is not Intent.OUT]
    outputs = [Field("handle", int, HANDLE, doc=f"handle to {fn.handle_type or 'object'}")]
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
            result["handle"] = handles.put(cell.value, owned=True)
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
    """creates / borrows / uses / destroys  handle-managed.

    SAFETY BUG THIS FIXES: this path never called check_exposable(). A function
    with a lifecycle (e.g. cJSON_PrintPreallocated, lifecycle="uses") skipped the
    fail-safe entirely, because policy was only enforced in the array/plain paths.
    Result: a non-const char* WRITE BUFFER param (role=OPAQUE, meant to be refused)
    was silently bound as a generic int64 in the .proto instead of being rejected.
    Every capability must clear the SAME policy regardless of which builder it
    goes through that is the whole point of a shared core.
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
        outputs = [Field("freed", int, SCALAR), Field("live_handles", int, SCALAR)]
        returns_mapping = True
    else:                                       # uses
        rt = py_restype(fn)
        outputs = [] if rt is type(None) else [Field("result", rt, STRING if rt is str else SCALAR)]
        returns_mapping = False

    def invoke(**kwargs):
        # OWNERSHIP: validate BEFORE the C call. Checking afterwards would already
        # have freed a borrowed pointer (a real double-free, observed in testing).
        if fn.lifecycle == "destroys":
            hid = kwargs[hkey[hparams[0].name]]
            if not handles.is_owned(hid):
                raise OwnershipError(
                    f"handle {hid} is BORROWED (owned by the library); freeing it "
                    f"would double-free. Delete its owner instead."
                )
        args = []
        for p in fn.params:
            if p.role is Role.HANDLE:
                args.append(handles.get(kwargs[hkey[p.name]]))
            else:
                args.append(to_c(kwargs[p.name], ctype_by_name(p.ctype)))
        ret = cfn(*args)

        if fn.lifecycle in ("creates", "borrows"):
            if not ret:
                return {"handle": None}
            owned = fn.lifecycle == "creates"
            hid = handles.put(ret, owned=owned)
            if owned:
                return {"handle": hid}
            return {"handle": hid, "borrowed": True,
                    "note": "owned by the library; do not free (delete its owner instead)"}
        if fn.lifecycle == "destroys":
            hid = kwargs[hkey[hparams[0].name]]
            handles.pop(hid)
            return {"freed": hid, "live_handles": len(handles)}
        # uses an OWNED string return is copied then the C buffer freed
        # (cJSON_Print's malloc'd result was previously leaked, bounded but real).
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



def build_capability(lib, fn: FunctionSpec, handles: HandleTable | None = None,
                     string_dealloc=None) -> Capability:
   
    check_exposable(fn)
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
   
    if handles is None:
        handles = HandleTable()
    string_dealloc = _find_string_deallocator(lib, spec)
    caps, refused = [], []
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