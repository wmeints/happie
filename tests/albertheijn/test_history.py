"""Tests for the pure purchase-history aggregation."""

from datetime import date

from happie.albertheijn._history import PurchaseRecord, aggregate


def record(
    day: date, key: str, name: str, quantity: float, amount: float
) -> PurchaseRecord:
    """Shorthand for one unified purchase record."""
    return PurchaseRecord(day=day, key=key, name=name, quantity=quantity, amount=amount)


def test_aggregate_merges_records_from_both_sources_per_key() -> None:
    """In-store and webshop records with the same key become one statistic."""
    window_start = date(2026, 5, 16)
    stats = aggregate(
        [
            record(date(2026, 6, 1), "wi111", "KAISERBROOD", 2.0, 2.38),
            record(date(2026, 6, 8), "wi111", "AH Kaiserbrood", 4.0, 4.76),
        ],
        window_start,
        days=90,
    )

    assert len(stats) == 1
    stat = stats[0]
    assert stat.key == "wi111"
    assert stat.total_quantity == 6.0
    # The longer name wins the merge.
    assert stat.name == "AH Kaiserbrood"


def test_aggregate_keeps_unconverted_pos_keys_separate() -> None:
    """A ``pos`` fallback key never merges with the same webshop key."""
    window_start = date(2026, 5, 16)
    stats = aggregate(
        [
            record(date(2026, 6, 1), "pos624318", "KAISERBROOD", 1.0, 1.19),
            record(date(2026, 6, 2), "wi624318", "Kaiserbrood", 1.0, 1.19),
        ],
        window_start,
        days=90,
    )

    assert [stat.key for stat in stats] == ["pos624318", "wi624318"]


def test_aggregate_dense_array_covers_whole_window() -> None:
    """The per-day array has one entry per window day, aligned to the start."""
    window_start = date(2026, 5, 16)
    stats = aggregate(
        [
            record(date(2026, 5, 16), "wi1", "Melk", 3.0, 3.0),
            record(date(2026, 6, 15), "wi1", "Melk", 2.0, 2.0),
        ],
        window_start,
        days=31,
    )

    stat = stats[0]
    assert stat.window_start == window_start
    assert len(stat.daily_counts) == 31
    # 2026-05-16 is the first day of the window; 2026-06-15 the last.
    assert stat.daily_counts[0] == 3.0
    assert stat.daily_counts[30] == 2.0
    assert sum(stat.daily_counts) == 5.0
    assert stat.purchase_days == 2


def test_aggregate_excludes_records_outside_the_window() -> None:
    """Records before the window start or past the last day contribute nothing."""
    window_start = date(2026, 5, 16)
    stats = aggregate(
        [
            record(date(2026, 5, 15), "wi1", "Melk", 9.0, 9.0),
            record(date(2026, 8, 14), "wi1", "Melk", 9.0, 9.0),
            record(date(2026, 8, 13), "wi2", "Kaas", 1.0, 1.0),
        ],
        window_start,
        days=90,
    )

    assert [stat.key for stat in stats] == ["wi2"]
    assert stats[0].total_quantity == 1.0


def test_aggregate_sums_spend_per_key() -> None:
    """Total spend is the sum of the per-record amounts."""
    window_start = date(2026, 5, 16)
    stats = aggregate(
        [
            record(date(2026, 6, 1), "wi1", "Melk", 1.0, 1.19),
            record(date(2026, 6, 2), "wi1", "Melk", 2.0, 2.38),
            record(date(2026, 6, 2), "wi2", "Kaas", 1.0, 4.5),
        ],
        window_start,
        days=90,
    )

    by_key = {stat.key: stat for stat in stats}
    assert by_key["wi1"].total_spend == 3.57
    assert by_key["wi2"].total_spend == 4.5


def test_aggregate_same_day_records_count_as_one_purchase_day() -> None:
    """Two records on the same day count as a single purchase day."""
    window_start = date(2026, 5, 16)
    stats = aggregate(
        [
            record(date(2026, 6, 1), "wi1", "Melk", 1.0, 1.0),
            record(date(2026, 6, 1), "wi1", "Melk", 2.0, 2.0),
        ],
        window_start,
        days=90,
    )

    stat = stats[0]
    assert stat.purchase_days == 1
    assert stat.total_quantity == 3.0


def test_aggregate_sorts_by_total_quantity_descending() -> None:
    """The result is ordered by total quantity, highest first."""
    window_start = date(2026, 5, 16)
    stats = aggregate(
        [
            record(date(2026, 6, 1), "wi1", "Melk", 2.0, 2.0),
            record(date(2026, 6, 1), "wi3", "Kaas", 5.0, 5.0),
            record(date(2026, 6, 1), "wi2", "Brood", 9.0, 9.0),
        ],
        window_start,
        days=90,
    )

    assert [stat.key for stat in stats] == ["wi2", "wi3", "wi1"]


def test_aggregate_empty_input_returns_empty_list() -> None:
    """No records at all yields no statistics."""
    assert aggregate([], date(2026, 5, 16), days=90) == []
