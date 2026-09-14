import asyncio
from datetime import date
from decimal import Decimal

from travel_agent.domain import BudgetConstraint, CostCategory, Money, Traveler, TripPlanRequest
from travel_agent.inventory import FakeInventory
from travel_agent.planner import TravelPlanner


def test_planner_builds_verified_five_day_family_plan() -> None:
    request = TripPlanRequest(
        origin="Chicago",
        destination="Washington, DC",
        start_date=date(2026, 10, 5),
        days=5,
        travelers=(Traveler(age=38), Traveler(age=37), Traveler(age=10), Traveler(age=7)),
        budget=BudgetConstraint(
            maximum=Money(amount=Decimal("4000"), currency="USD"),
            included_categories=frozenset(
                {
                    CostCategory.TRANSPORT,
                    CostCategory.LODGING,
                    CostCategory.LOCAL_TRANSPORT,
                    CostCategory.ACTIVITIES,
                    CostCategory.MEALS,
                }
            ),
            contingency=Money(amount=Decimal("200"), currency="USD"),
        ),
    )

    plan, verification = asyncio.run(TravelPlanner(FakeInventory()).plan(request))

    assert verification.accepted
    assert verification.total.amount == Decimal("4000")
    assert len(plan.days) == 5
    assert plan.days[0].local_date == date(2026, 10, 5)
    assert plan.days[-1].local_date == date(2026, 10, 9)
    assert {offer.offer_id for offer in plan.selected_offers} == {
        "activities",
        "local-pass",
        "lodging-family",
        "meals",
        "transport-basic",
    }
    assert all(offer.expires_at > offer.observed_at for offer in plan.selected_offers)