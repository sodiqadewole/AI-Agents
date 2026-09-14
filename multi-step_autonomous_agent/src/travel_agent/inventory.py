from decimal import Decimal
from typing import Protocol

from travel_agent.domain import CostCategory, Money, Offer, TripPlanRequest


class InventoryGateway(Protocol):
    async def search(self, request: TripPlanRequest) -> tuple[Offer, ...]: ...


class FakeInventory:
    async def search(self, request: TripPlanRequest) -> tuple[Offer, ...]:
        currency = request.budget.maximum.currency
        return (
            self._offer(
                "transport-basic",
                CostCategory.TRANSPORT,
                "Round-trip transport",
                "1200",
                currency,
            ),
            self._offer(
                "transport-flex",
                CostCategory.TRANSPORT,
                "Flexible transport",
                "1500",
                currency,
            ),
            self._offer(
                "lodging-family",
                CostCategory.LODGING,
                "Four-night family lodging",
                "1600",
                currency,
            ),
            self._offer(
                "lodging-central",
                CostCategory.LODGING,
                "Central family lodging",
                "1900",
                currency,
            ),
            self._offer(
                "local-pass",
                CostCategory.LOCAL_TRANSPORT,
                "Five-day local transit",
                "200",
                currency,
            ),
            self._offer(
                "activities",
                CostCategory.ACTIVITIES,
                "Family activity bundle",
                "300",
                currency,
            ),
            self._offer("meals", CostCategory.MEALS, "Estimated family meals", "500", currency),
            self._offer("insurance", CostCategory.INSURANCE, "Travel insurance", "100", currency),
        )

    @staticmethod
    def _offer(
        offer_id: str,
        category: CostCategory,
        title: str,
        amount: str,
        currency: str,
    ) -> Offer:
        return Offer.fresh_for_demo(
            offer_id=offer_id,
            category=category,
            title=title,
            price=Money(amount=Decimal(amount), currency=currency),
        )