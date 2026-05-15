"""Tests for ``SymbolMaskTable`` — process-scoped symbol → STK-* label mapping.

Spec: openspec/changes/web-public-shell-and-mask/specs/eventbus-public-mask/spec.md
      ("SymbolMaskTable labels are stable in-instance and base-26-encoded")
"""

from __future__ import annotations

from ohmystock.eventbus.mask_table import SymbolMaskTable


def test_first_three_distinct_symbols_get_sequential_labels() -> None:
    t = SymbolMaskTable({})
    assert t.mask("2330") == "STK-A"
    assert t.mask("2317") == "STK-B"
    assert t.mask("2454") == "STK-C"


def test_same_symbol_returns_same_label() -> None:
    t = SymbolMaskTable({})
    first = t.mask("2330")
    second = t.mask("2330")
    assert first == second == "STK-A"


def test_27th_distinct_symbol_rolls_over_to_stk_aa() -> None:
    t = SymbolMaskTable({})
    labels = [t.mask(f"sym{i}") for i in range(27)]
    assert labels[0] == "STK-A"
    assert labels[25] == "STK-Z"
    assert labels[26] == "STK-AA"


def test_53rd_distinct_symbol_rolls_into_stk_ba() -> None:
    """Sanity-check base-26 walks past the first double-letter row."""
    t = SymbolMaskTable({})
    labels = [t.mask(f"sym{i}") for i in range(53)]
    assert labels[51] == "STK-AZ"
    assert labels[52] == "STK-BA"


def test_industry_of_returns_mapped_value() -> None:
    t = SymbolMaskTable({"2330": "半導體", "2882": "金融"})
    assert t.industry_of("2330") == "半導體"
    assert t.industry_of("2882") == "金融"


def test_industry_of_falls_through_to_other_on_miss() -> None:
    t = SymbolMaskTable({"2330": "半導體"})
    assert t.industry_of("9999") == "其他"


def test_two_instances_do_not_share_state() -> None:
    t1 = SymbolMaskTable({})
    t1.mask("2330")
    t2 = SymbolMaskTable({})
    # Fresh instance MUST start counter at A regardless of t1's state.
    assert t2.mask("2454") == "STK-A"
    assert t2.mask("1101") == "STK-B"
