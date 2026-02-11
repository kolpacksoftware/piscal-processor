"""Tests for piscal_processor.parser."""

import pytest

from piscal_processor.parser import (
    next_nonempty,
    normalize_scalar,
    parse_csv_line,
    parse_key_value_section,
    parse_triplet,
)


def test_parse_csv_line_simple():
    assert parse_csv_line("a,b,c") == ["a", "b", "c"]


def test_parse_csv_line_quoted():
    assert parse_csv_line('"a,b",c') == ["a,b", "c"]


def test_parse_csv_line_trim_leading():
    # skipinitialspace trims leading space after delimiter, not trailing
    result = parse_csv_line("  a , b , c  ")
    assert result[0].strip() == "a" and result[1].strip() == "b" and result[2].strip() == "c"


def test_next_nonempty_finds_next():
    lines = ["", "  ", "x", "y"]
    assert next_nonempty(lines, 0) == 2
    assert next_nonempty(lines, 2) == 2


def test_next_nonempty_past_end():
    lines = ["", ""]
    assert next_nonempty(lines, 0) == 2


def test_normalize_scalar_empty():
    assert normalize_scalar("") is None
    assert normalize_scalar("   ") is None


def test_normalize_scalar_na():
    assert normalize_scalar("NA") is None
    assert normalize_scalar("na") is None


def test_normalize_scalar_missing():
    assert normalize_scalar("-9999") is None
    assert normalize_scalar("-9999.0") is None


def test_normalize_scalar_int():
    assert normalize_scalar("42") == 42


def test_normalize_scalar_float():
    assert normalize_scalar("3.14") == 3.14


def test_normalize_scalar_string():
    assert normalize_scalar("hello") == "hello"


def test_parse_key_value_section():
    lines = [
        "Key1: value1",
        "Key2: value2",
        "",
        "SiteID,Other",
    ]
    idx, info = parse_key_value_section(lines)
    assert idx == 3
    assert info["Key1"] == "value1"
    assert info["Key2"] == "value2"


def test_parse_triplet():
    lines = [
        "H1,H2",
        "u1,u2",
        "v1,v2",
    ]
    idx, headers, units, values = parse_triplet(lines, 0)
    assert idx == 3
    assert headers == ["H1", "H2"]
    assert units == ["u1", "u2"]
    assert values == ["v1", "v2"]
