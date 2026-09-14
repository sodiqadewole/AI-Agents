from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
NonNegativeAmount = Annotated[Decimal, Field(ge=Decimal("0"), max_digits=12, decimal_places=2)]


class CostCategory(StrEnum):
    TRANSPORT = "transport"
    LODGING = "lodging"
    LOCAL_TRANSPORT = "local_transport"
    ACTIVITIES = "activities"
    MEALS = "meals"
    INSURANCE = "insurance"
    OTHER = "other"


class Money(StrictModel):
    amount: NonNegativeAmount
    currency: Currency


class Traveler(StrictModel):
    age: Annotated[int, Field(ge=0, le=125)]


class BudgetConstraint(StrictModel):
    maximum: Money
    included_categories: frozenset[CostCategory]
    contingency: Money

    @model_validator(mode="after")
    def currencies_match(self) -> BudgetConstraint:
        if self.maximum.currency != self.contingency.currency:
            raise ValueError("budget and contingency currencies must match")
        if self.contingency.amount > self.maximum.amount:
            raise ValueError("contingency cannot exceed the maximum budget")
        return self


class TripPlanRequest(StrictModel):
    origin: Annotated[str, Field(min_length=2, max_length=100)]
    destination: Annotated[str, Field(min_length=2, max_length=100)]
    start_date: date
    days: Annotated[int, Field(ge=1, le=30)] = 5
    travelers: Annotated[tuple[Traveler, ...], Field(min_length=1, max_length=12)]
    budget: BudgetConstraint
    preferences: tuple[str, ...] = ()


class Offer(StrictModel):
    offer_id: str
    category: CostCategory
    title: str
    price: Money
    observed_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def has_valid_freshness_window(self) -> Offer:
        if self.observed_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("offer timestamps must be timezone-aware")
        if self.expires_at <= self.observed_at:
            raise ValueError("offer expiration must follow observation time")
        return self

    @classmethod
    def fresh_for_demo(
        cls,
        *,
        offer_id: str,
        category: CostCategory,
        title: str,
        price: Money,
    ) -> Offer:
        observed_at = datetime.now(UTC)
        return cls(
            offer_id=offer_id,
            category=category,
            title=title,
            price=price,
            observed_at=observed_at,
            expires_at=observed_at + timedelta(minutes=15),
        )


class CostItem(StrictModel):
    category: CostCategory
    description: str
    amount: Money
    offer_id: str | None = None
    estimated: bool = False


class TripCostLedger(StrictModel):
    items: tuple[CostItem, ...]
    contingency: Money
    unknown_required_categories: frozenset[CostCategory] = frozenset()

    @model_validator(mode="after")
    def currencies_match(self) -> TripCostLedger:
        currencies = {item.amount.currency for item in self.items}
        currencies.add(self.contingency.currency)
        if len(currencies) != 1:
            raise ValueError("all ledger amounts must use one budget currency")
        return self

    @property
    def total(self) -> Money:
        amount = sum((item.amount.amount for item in self.items), start=Decimal("0"))
        return Money(amount=amount + self.contingency.amount, currency=self.contingency.currency)


class DailyPlan(StrictModel):
    local_date: date
    title: str
    activities: tuple[str, ...] = ()


class TripPlan(StrictModel):
    request: TripPlanRequest
    days: tuple[DailyPlan, ...]
    selected_offers: tuple[Offer, ...]
    ledger: TripCostLedger


class BudgetVerification(StrictModel):
    accepted: bool
    total: Money
    maximum: Money
    remaining: Money
    reasons: tuple[str, ...]