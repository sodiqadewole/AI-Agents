from decimal import Decimal

from travel_agent.domain import BudgetVerification, Money, TripCostLedger, TripPlanRequest


def verify_budget(request: TripPlanRequest, ledger: TripCostLedger) -> BudgetVerification:
    maximum = request.budget.maximum
    total = ledger.total
    reasons: list[str] = []

    if total.currency != maximum.currency:
        reasons.append("ledger currency does not match the budget currency")

    if ledger.contingency != request.budget.contingency:
        reasons.append("ledger contingency does not match the requested reserve")

    missing_categories = request.budget.included_categories - {
        item.category for item in ledger.items
    }
    unknown_categories = ledger.unknown_required_categories & request.budget.included_categories

    if missing_categories:
        missing = ", ".join(sorted(category.value for category in missing_categories))
        reasons.append(f"required cost categories are missing: {missing}")

    if unknown_categories:
        unknown = ", ".join(sorted(category.value for category in unknown_categories))
        reasons.append(f"required cost categories are unknown: {unknown}")

    if total.amount > maximum.amount:
        reasons.append("trip total exceeds the fixed budget")

    remaining_amount = max(maximum.amount - total.amount, Decimal("0"))
    return BudgetVerification(
        accepted=not reasons,
        total=total,
        maximum=maximum,
        remaining=Money(amount=remaining_amount, currency=maximum.currency),
        reasons=tuple(reasons),
    )