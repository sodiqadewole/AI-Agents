from datetime import date
from decimal import Decimal

from travel_agent.budget import verify_budget
from travel_agent.domain import (
    BudgetConstraint,
    CostCategory,
    CostItem,
    Money,
    Traveler,
    TripCostLedger,
    TripPlanRequest,
)


def _request(maximum: str = "4000") -> TripPlanRequest:
    currency = "USD"
    return TripPlanRequest(
        origin="Chicago",
        destination="Washington, DC",
        start_date=date(2026, 10, 5),
        travelers=(Traveler(age=38), Traveler(age=37), Traveler(age=10), Traveler(age=7)),
        budget=BudgetConstraint(
            maximum=Money(amount=Decimal(maximum), currency=currency),
            included_categories=frozenset(
                {CostCategory.TRANSPORT, CostCategory.LODGING, CostCategory.MEALS}
            ),
            contingency=Money(amount=Decimal("200"), currency=currency),
        ),
    )


def _ledger(*, meals: str = "500", unknown: bool = False) -> TripCostLedger:
    currency = "USD"
    return TripCostLedger(
        items=(
            CostItem(
                category=CostCategory.TRANSPORT,
                description="Transport",
                amount=Money(amount=Decimal("1200"), currency=currency),
            ),
            CostItem(
                category=CostCategory.LODGING,
                description="Lodging",
                amount=Money(amount=Decimal("1600"), currency=currency),
            ),
            CostItem(
                category=CostCategory.MEALS,
                description="Meals",
                amount=Money(amount=Decimal(meals), currency=currency),
                estimated=True,
            ),
        ),
        contingency=Money(amount=Decimal("200"), currency=currency),
        unknown_required_categories=(
            frozenset({CostCategory.MEALS}) if unknown else frozenset()
        ),
    )


def test_accepts_complete_ledger_under_fixed_budget() -> None:
    verification = verify_budget(_request(), _ledger())

    assert verification.accepted
    assert verification.total.amount == Decimal("3500")
    assert verification.remaining.amount == Decimal("500")
    assert verification.reasons == ()


def test_rejects_unknown_required_cost_even_when_total_is_low() -> None:
    verification = verify_budget(_request(), _ledger(unknown=True))

    assert not verification.accepted
    assert verification.reasons == ("required cost categories are unknown: meals",)


def test_rejects_plan_over_fixed_budget() -> None:
    verification = verify_budget(_request(maximum="3200"), _ledger())

    assert not verification.accepted
    assert "trip total exceeds the fixed budget" in verification.reasons