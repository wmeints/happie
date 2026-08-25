"""Pure aggregation of unified purchase records into per-product statistics.

No I/O in this module: it receives already-normalised records from the
receipt and order sources and turns them into :class:`PurchaseStat` objects.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from happie.albertheijn._models import PurchaseStat

__all__ = ["PurchaseRecord", "aggregate"]


@dataclass(frozen=True)
class PurchaseRecord:
    """One unified purchase record from either source.

    Attributes:
        day: The calendar day of the purchase.
        key: The canonical product key (``wi<webshop_id>`` or
            ``pos<pos_id>``).
        name: The product name as known by the source.
        quantity: The quantity purchased.
        amount: The amount spent on this purchase.
    """

    day: date
    key: str
    name: str
    quantity: float
    amount: float


def aggregate(
    records: Sequence[PurchaseRecord], window_start: date, days: int
) -> list[PurchaseStat]:
    """Aggregate purchase records into one :class:`PurchaseStat` per product.

    Records whose day falls outside the window
    (``[window_start, window_start + days - 1]``) are ignored. Records with
    the same key merge into one statistic: quantities and spend sum, the
    longest known name is kept, and every window day gets exactly one dense
    per-day entry (zero where nothing was bought).

    Args:
        records: The unified purchase records, from both sources.
        window_start: The first calendar day of the window.
        days: The length of the window in days.

    Returns:
        One statistic per product, sorted by total quantity descending
        (ties broken by product key for a deterministic order).
    """
    totals: dict[str, dict] = {}
    for record in records:
        offset = (record.day - window_start).days
        if not 0 <= offset < days:
            continue
        entry = totals.setdefault(
            record.key,
            {"name": "", "quantity": 0.0, "spend": 0.0, "per_day": [0.0] * days},
        )
        entry["quantity"] += record.quantity
        entry["spend"] += record.amount
        entry["per_day"][offset] += record.quantity
        if len(record.name) > len(entry["name"]):
            entry["name"] = record.name

    stats = [
        PurchaseStat(
            key=key,
            name=entry["name"],
            total_quantity=entry["quantity"],
            purchase_days=sum(count > 0 for count in entry["per_day"]),
            total_spend=entry["spend"],
            window_start=window_start,
            daily_counts=tuple(entry["per_day"]),
        )
        for key, entry in totals.items()
    ]
    return sorted(stats, key=lambda stat: (-stat.total_quantity, stat.key))
