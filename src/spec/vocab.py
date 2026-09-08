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
    CALLBACK = "callback"
    OPAQUE = "opaque"