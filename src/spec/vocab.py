"""The closed vocabulary of the capability spec (Shroud/SAL-derived)."""
from enum import Enum


class Intent(str, Enum):
    IN = "in"
    OUT = "out"
    INOUT = "inout"


class Role(str, Enum):
    SCALAR = "scalar"       # int/float/bool/char value
    STRING = "string"       # const char*
    ARRAY = "array"         # T* with a companion length 
    LENGTH_OF = "length_of" # the integer giving an array's length 
    BUFFER = "buffer"       # caller-sized char* out 
    HANDLE = "handle"       # opaque pointer with a lifecycle 
    OUT_HANDLE = "out_handle"  # T** that RECEIVES a new handle 
    CALLBACK = "callback"   # function pointer  flagged, not exposable
    OPAQUE = "opaque"       # unknown/unhandled pointer