"""
Tests for the test-suite-reuse extractor (paper section 5): it must correctly
classify a library's own Unity assertions as mechanically reusable against a
Ferrule binding, or blocked with a specific reason. The single most important
correctness property is that a WHITE-BOX assertion (asserting on an internal
struct field the binding does not expose) is never misclassified as reusable,
since that would silently overstate how much of a suite the methodology covers.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ferrule.reuse.extract import (
    extract_file, summarize, strip_comments_and_strings_aware, _classify, Assertion,
)


def classify(macro, arg, prefix="cJSON"):
    a = Assertion(macro=macro, raw_arg=arg)
    _classify(a, prefix)
    return a


def test_black_box_single_call_literal_args_is_reusable():
    a = classify("TEST_ASSERT_NULL", 'cJSON_GetObjectItem(NULL, "STR")')
    assert a.reusable
    assert a.call == "cJSON_GetObjectItem"

def test_no_arg_call_is_reusable():
    a = classify("TEST_ASSERT_NOT_NULL", "cJSON_CreateObject()")
    assert a.reusable
    assert a.call == "cJSON_CreateObject"

def test_struct_arrow_access_is_blocked_whitebox():
    a = classify("TEST_ASSERT_NULL", "item->child")
    assert not a.reusable
    assert a.reason.startswith("white-box")

def test_eq_macro_struct_access_in_first_operand_is_blocked():
    """THE critical case: TEST_ASSERT_EQUAL_INT(number->type, cJSON_Number).
    The struct read is the FIRST operand; scanning only the second would
    wrongly call this reusable."""
    a = classify("TEST_ASSERT_EQUAL_INT", "number->type, cJSON_Number")
    assert not a.reusable
    assert a.reason.startswith("white-box")

def test_eq_macro_struct_access_with_literal_expected_is_blocked():
    """TEST_ASSERT_EQUAL_DOUBLE(number->valuedouble, 42): the '42' is a literal
    but the FIRST operand is a struct read -- must still be blocked."""
    a = classify("TEST_ASSERT_EQUAL_DOUBLE", "number->valuedouble, 42")
    assert not a.reusable
    assert a.reason.startswith("white-box")

def test_variable_argument_is_blocked_needs_state():
    a = classify("TEST_ASSERT_NULL", "cJSON_GetObjectItem(item, NULL)")
    assert not a.reusable
    assert "not a literal" in a.reason

def test_non_library_call_is_blocked():
    a = classify("TEST_ASSERT_TRUE", 'strcmp(str, "STR") == 0')
    assert not a.reusable
    assert "not a cJSON" in a.reason

def test_call_with_trailing_arithmetic_is_blocked():
    a = classify("TEST_ASSERT_NULL", "cJSON_GetArrayItem(NULL, 0) + 1")
    assert not a.reusable

def test_float_literal_dot_is_not_mistaken_for_struct_access():
    """A float literal like 1.5 must not trip the '.' struct-access check."""
    a = classify("TEST_ASSERT_EQUAL_DOUBLE", "1.5, cJSON_GetNumberValue(NULL)")
    # first operand is a float literal (not struct access); second is a clean
    # library call over a literal -> reusable
    assert a.reusable, a.reason

def test_string_paren_does_not_break_bracket_matching():
    """A ')' inside a string literal must not be seen as closing the macro."""
    src = 'static void t(void){ TEST_ASSERT_NULL(cJSON_Parse(")not real")); }'
    with tempfile.NamedTemporaryFile("w", suffix=".c", delete=False) as f:
        f.write(src)
        path = f.name
    tests = extract_file(path)
    assert len(tests) == 1
    assert len(tests[0].assertions) == 1

def test_comment_with_arrow_is_ignored():
    """A '->' inside a comment must not make a clean assertion look white-box."""
    src = ('static void t(void){ /* sets item->type */ '
           'TEST_ASSERT_NULL(cJSON_GetArrayItem(NULL, 0)); }')
    with tempfile.NamedTemporaryFile("w", suffix=".c", delete=False) as f:
        f.write(src)
        path = f.name
    tests = extract_file(path)
    assert tests[0].assertions[0].reusable

def test_summary_counts_add_up():
    src = """
    static void t(void){
        TEST_ASSERT_NULL(cJSON_GetArrayItem(NULL, 0));
        TEST_ASSERT_NULL(item->child);
    }
    """
    with tempfile.NamedTemporaryFile("w", suffix=".c", delete=False) as f:
        f.write(src)
        path = f.name
    s = summarize(extract_file(path))
    assert s["assertions_total"] == 2
    assert s["assertions_reusable"] == 1
    assert s["assertions_blocked"] == 1
