"""The closed vocabulary of the capability spec (Shroud/SAL-derived)."""
from enum import Enum


class Intent(str, Enum):
    IN = "in"
    OUT = "out"
    INOUT = "inout"


class Role(str, Enum):
    SCALAR = "scalar"
    STRING = "string"
    ARRAY = "array"
    LENGTH_OF = "length_of"
    BUFFER = "buffer"
    HANDLE = "handle"
    OUT_HANDLE = "out_handle"
    CALLER_STATE = "caller_state"   # struct the BINDING allocates, the library initializes
    CALLBACK = "callback"
    OPAQUE = "opaque"


class Owner(str, Enum):
    """Who is responsible for freeing a handle.

    CALLER and LIBRARY are the two values the paper defines; SHARED is a
    minimal extension for reference-counted APIs (libgit2) where both caller
    and library hold a reference and each frees independently.
    """
    CALLER = "caller"      # caller must free; freeing destroys the object
    LIBRARY = "library"    # borrowed; caller must never free
    SHARED = "shared"      # refcounted: caller MUST release its reference, and
                           # releasing does NOT destroy the object for others