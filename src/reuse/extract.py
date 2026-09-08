"""
Extract a C library's own unit-test assertions and classify each as either
mechanically reusable against a Ferrule binding, or blocked (with a reason).

This deliberately does NOT use libclang or a full C parser, for two reasons
specific to this task:

  1. The pattern we match IS the Unity macro call, `TEST_ASSERT_NULL(...)`.
     Any real parse preprocesses the file, which EXPANDS those macros into
     `if`/`UnityAssert...` machinery and destroys the pattern. We need the
     macros intact.
  2. The task is lexically regular: find `TEST_ASSERT_<kind>( <arg> )` where
     <arg> is a literal or a single function call over literals. That is a
     bracket-matching problem over a token stream, not one needing C
     semantics. A C-aware tokenizer (handling strings, chars, comments,
     nested parens) is the right precision.

The output is a classification, and the *distribution* of classifications is
itself the reportable result: how much of a real suite is black-box reusable
versus blocked by white-box struct access, chaining, or unsupported inputs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


def strip_comments_and_strings_aware(src: str) -> str:
    """Return src with comments removed but string/char literals preserved
    (their contents replaced by a placeholder so a ')' or '->' inside a string
    can never be mistaken for real syntax)."""
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        two = src[i:i+2]
        if two == "//":
            j = src.find("\n", i)
            i = n if j == -1 else j
        elif two == "/*":
            j = src.find("*/", i+2)
            i = n if j == -1 else j + 2
        elif c == '"' or c == "'":
            quote = c
            out.append(quote)
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == quote:
                    break
                i += 1
            out.append("STR" if quote == '"' else "CH")
            out.append(quote)
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _match_paren(src: str, open_idx: int) -> int:
    """Given index of a '(', return index of the matching ')', or -1."""
    depth = 0
    i, n = open_idx, len(src)
    while i < n:
        c = src[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


@dataclass
class Assertion:
    macro: str
    raw_arg: str
    reusable: bool = False
    reason: str = ""
    call: str | None = None
    call_args: list = field(default_factory=list)
    expected: str | None = None


@dataclass
class TestFunction:
    name: str
    assertions: list = field(default_factory=list)


_NULL_MACROS = {"TEST_ASSERT_NULL": "null", "TEST_ASSERT_NOT_NULL": "not_null"}
_BOOL_MACROS = {"TEST_ASSERT_TRUE": "true", "TEST_ASSERT_FALSE": "false"}
_EQ_MACROS = {
    "TEST_ASSERT_EQUAL_INT": "int", "TEST_ASSERT_EQUAL": "int",
    "TEST_ASSERT_EQUAL_DOUBLE": "double", "TEST_ASSERT_EQUAL_STRING": "string",
}
_ALL_MACROS = set(_NULL_MACROS) | set(_BOOL_MACROS) | set(_EQ_MACROS)


_FUNC_DEF = re.compile(r"static\s+void\s+([A-Za-z_]\w*)\s*\(\s*void\s*\)\s*\{")
_CALL = re.compile(r"^\s*([A-Za-z_]\w*)\s*\(")


def extract_file(path: str, lib_prefix: str = "cJSON") -> list[TestFunction]:
    """Parse a Unity test .c file into TestFunctions with classified Assertions."""
    with open(path, "r", errors="replace") as f:
        raw = f.read()
    src = strip_comments_and_strings_aware(raw)

    tests: list[TestFunction] = []
    for m in _FUNC_DEF.finditer(src):
        name = m.group(1)
        body_start = m.end() - 1
        body_end = _match_brace(src, body_start)
        if body_end == -1:
            continue
        body = src[body_start + 1:body_end]
        tf = TestFunction(name=name)
        for a in _extract_assertions(body, lib_prefix):
            tf.assertions.append(a)
        if tf.assertions:
            tests.append(tf)
    return tests


def _match_brace(src: str, open_idx: int) -> int:
    depth = 0
    i, n = open_idx, len(src)
    while i < n:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _extract_assertions(body: str, lib_prefix: str) -> list[Assertion]:
    results = []
    for m in re.finditer(r"\b(TEST_ASSERT[A-Z_]*)\s*\(", body):
        macro = m.group(1)
        if macro not in _ALL_MACROS:
            continue
        open_idx = m.end() - 1
        close_idx = _match_paren(body, open_idx)
        if close_idx == -1:
            continue
        arg = body[open_idx + 1:close_idx].strip()
        a = Assertion(macro=macro, raw_arg=arg)
        _classify(a, lib_prefix)
        results.append(a)
    return results


def _split_top_level_commas(s: str) -> list[str]:
    """Split on commas not nested inside parentheses."""
    parts, depth, cur = [], 0, []
    for c in s:
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
    if cur:
        parts.append("".join(cur).strip())
    return parts


_LITERAL = re.compile(r"""^(
    NULL |
    -?\d+ |                    # int
    -?\d*\.\d+ |               # float
    "STR" |                    # our placeholder for a string literal
    'CH' |                     # char literal placeholder
    true | false | 0 | 1
)$""", re.X)


def _is_literal(tok: str) -> bool:
    return bool(_LITERAL.match(tok.strip()))


def _has_struct_access(s: str) -> bool:
    return "->" in s or bool(re.search(r"[A-Za-z_]\w*\s*\.\s*[A-Za-z_]", s))


def _classify(a: Assertion, lib_prefix: str) -> None:
    """Decide whether this assertion is mechanically reusable, and why/why not.
    Sets a.reusable and a.reason (and a.call / a.expected when recognized)."""
    if a.macro in _EQ_MACROS:
        parts = _split_top_level_commas(a.raw_arg)
        if len(parts) != 2:
            a.reason = "EQUAL macro without exactly two operands"
            return
        if _has_struct_access(parts[0]) or _has_struct_access(parts[1]):
            a.reason = "white-box: asserts on a struct field the binding does not expose"
            return
        if _CALL.match(parts[1]) and parts[1].lstrip().startswith(("cJSON", lib_prefix)):
            a.expected, operand = parts[0], parts[1]
        elif _CALL.match(parts[0]) and parts[0].lstrip().startswith(("cJSON", lib_prefix)):
            a.expected, operand = parts[1], parts[0]
        else:
            a.expected, operand = parts[0], parts[1]
    else:
        operand = a.raw_arg
        if _has_struct_access(operand):
            a.reason = "white-box: asserts on a struct field the binding does not expose"
            return

    if _is_literal(operand):
        a.reusable = True
        a.reason = "literal operand"
        return

    cm = _CALL.match(operand)
    if not cm:
        a.reason = "operand is not a single library call (variable, cast, or expression)"
        return
    callee = cm.group(1)
    if not callee.startswith(lib_prefix):
        a.reason = f"operand calls '{callee}', not a {lib_prefix} function"
        return

    call_open = operand.index("(")
    call_close = _match_paren(operand, call_open)
    if call_close != len(operand) - 1:
        a.reason = "operand is a call combined with more expression (chaining/arithmetic)"
        return

    inner = operand[call_open + 1:call_close].strip()
    call_args = _split_top_level_commas(inner) if inner else []

    for arg in call_args:
        if not _is_literal(arg):
            a.reason = (f"call argument {arg!r} is not a literal "
                        f"(nested call or variable -> needs state reconstruction)")
            a.call = callee
            return

    a.reusable = True
    a.call = callee
    a.call_args = call_args
    a.reason = "black-box: single library call over literal arguments"


def summarize(tests: list[TestFunction]) -> dict:
    total = reusable = 0
    reasons: dict[str, int] = {}
    for tf in tests:
        for a in tf.assertions:
            total += 1
            if a.reusable:
                reusable += 1
            else:
                key = a.reason.split(":")[0]
                reasons[key] = reasons.get(key, 0) + 1
    return {
        "test_functions": len(tests),
        "assertions_total": total,
        "assertions_reusable": reusable,
        "assertions_blocked": total - reusable,
        "blocked_reasons": reasons,
    }
