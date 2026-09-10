"""Contract for the M3 selection-size split (bd 4zg / 8an.1.7, NORTHSTAR §4, §9).

bd 8an.1.7 (M0g) characterized the radius lever as scale-stable for n>=100 but
STRUCTURALLY compressed at n<100 (n=10: f~0.5, ~38-56% radius compression,
NORTHSTAR §4) — an effect the bias formula cannot fix. The consequence (bd 4zg)
is that the M3 population search must EXCLUDE the small-n regime from selection
and iterate on n>=100. ``benchmarks.scale_invariance.selection_sizes`` is the
single source of truth for that split (consumed by the characterization report
and, later, the M3 agent loop). These tests pin the contract so the n=10
exclusion can never silently regress.
"""
from benchmarks.scale_invariance import (
    selection_sizes,
    SCALE_STABLE_MIN_N,
    INNER_LOOP_MAX_N,
)


def test_constants_match_m0g_finding():
    assert SCALE_STABLE_MIN_N == 100   # below this = small-n compression (bd 4zg)
    assert INNER_LOOP_MAX_N == 1000


def test_default_split_matches_characterization():
    """Must reproduce the exact split scale_invariance_characterization.py emitted
    inline before the refactor (so the on-demand report is unchanged)."""
    s = selection_sizes([10, 100, 1000, 3000])
    assert s["scale_stable"] == [100, 1000, 3000]
    assert s["inner_loop"] == [100, 1000]
    assert s["validation"] == [1000, 3000]   # 1000 is shared boundary (>= inner_loop_max)
    assert s["excluded_small_n"] == [10]


def test_n10_and_all_small_n_are_excluded_from_selection():
    """The core 4zg invariant: nothing below SCALE_STABLE_MIN_N may be selected."""
    s = selection_sizes([1, 10, 50, 99, 100, 200])
    for n in (1, 10, 50, 99):
        assert n not in s["scale_stable"]
        assert n not in s["inner_loop"]
        assert n not in s["validation"]
        assert n in s["excluded_small_n"]
    assert 100 in s["inner_loop"] and 200 in s["inner_loop"]


def test_inner_loop_is_bounded_subset_of_scale_stable():
    s = selection_sizes([10, 100, 500, 1000, 3000])
    assert set(s["inner_loop"]) <= set(s["scale_stable"])
    assert all(SCALE_STABLE_MIN_N <= n <= INNER_LOOP_MAX_N for n in s["inner_loop"])
    assert all(n >= SCALE_STABLE_MIN_N for n in s["scale_stable"])


def test_custom_inner_loop_max():
    s = selection_sizes([100, 500, 1000, 3000], inner_loop_max=500)
    assert s["inner_loop"] == [100, 500]
    assert s["validation"] == [500, 1000, 3000]   # >= inner_loop_max
    assert s["scale_stable"] == [100, 500, 1000, 3000]


def test_empty_and_all_small_inputs():
    assert selection_sizes([]) == {
        "scale_stable": [], "inner_loop": [], "validation": [], "excluded_small_n": [],
    }
    s = selection_sizes([10])
    assert s["scale_stable"] == [] and s["inner_loop"] == []
    assert s["excluded_small_n"] == [10]


def test_preserves_input_order():
    s = selection_sizes([3000, 100, 1000])
    assert s["scale_stable"] == [3000, 100, 1000]
    assert s["inner_loop"] == [100, 1000]
