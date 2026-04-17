"""Repository-layer hygiene tests for Order (Slice 6 / H14).

Purpose
-------
Enforce that ``OrderRepository`` never re-grows a direct status-write
method that bypasses the Punzierungs-Check guard that lives inside
``OrderService.update_order`` (M4 / R8 / A5.3).

Background
----------
``OrderRepository.change_order_status`` previously performed a direct
``setattr(order, 'status', ...)`` which bypassed the M4 guard. It was
removed in Slice 6 (H14 cleanup) after a static search confirmed zero
callers in ``src/`` and ``tests/``.

If a future contributor re-introduces ``change_order_status`` (or a
similarly-named status-write method) on the repository class these
tests will fail loudly and they must rewrite the caller to go through
``OrderService.update_order``.

All Order status transitions MUST flow through
``OrderService.update_order`` (called by PUT/PATCH /orders/{id} and the
scan flow's ``OrderService.advance_status``) so that the Punzierungs
guard fires uniformly.
"""
from __future__ import annotations

from goldsmith_erp.db.repositories.order import OrderRepository


class TestOrderRepositoryNoStatusWriteMethods:
    """The repository must not offer a status-write method that would
    bypass OrderService.update_order and its Punzierungs guard."""

    def test_change_order_status_removed(self):
        """H14 — the deleted method must not come back."""
        assert not hasattr(OrderRepository, "change_order_status"), (
            "OrderRepository.change_order_status was deleted in Slice 6 "
            "(H14) because it bypassed the Punzierungs-Check guard. "
            "If you need to transition an Order status, call "
            "OrderService.update_order or OrderService.advance_status "
            "— they enforce M4/R8/A5.3."
        )

    def test_change_status_alias_also_absent(self):
        """Defend against the short-name variant the original plan
        referenced (``change_status``). Keeping both out of the
        namespace makes the invariant clearer to grep for."""
        assert not hasattr(OrderRepository, "change_status"), (
            "OrderRepository.change_status is also banned — any "
            "status transition must go through OrderService."
        )

    def test_advance_status_not_on_repository(self):
        """``advance_status`` belongs on the service, not the
        repository. Keeping it off the repository prevents someone
        accidentally reaching for a bypass method."""
        assert not hasattr(OrderRepository, "advance_status"), (
            "advance_status is a service-layer method (OrderService). "
            "Do not add it to OrderRepository."
        )
