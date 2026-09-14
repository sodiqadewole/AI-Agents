from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol

from pydantic import Field, ValidationError

from travel_agent.domain import (
    BudgetConstraint,
    CostCategory,
    Currency,
    Money,
    StrictModel,
    Traveler,
    TripPlanRequest,
)


class StructuredModelGateway(Protocol):
    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, object],
    ) -> dict[str, object]: ...


class ExtractedTripRequest(StrictModel):
    origin: str | None = None
    destination: str | None = None
    start_date: date | None = None
    days: int | None = Field(default=None, ge=1, le=30)
    traveler_ages: tuple[int, ...] | None = None
    maximum_budget: Decimal | None = Field(default=None, ge=Decimal("0"))
    currency: Currency | None = None
    included_categories: frozenset[CostCategory] | None = None
    contingency: Decimal | None = Field(default=None, ge=Decimal("0"))
    preferences: tuple[str, ...] | None = None


class RequestParseResult(StrictModel):
    request: TripPlanRequest | None
    questions: tuple[str, ...]


class NaturalLanguageRequestParser:
    def __init__(self, gateway: StructuredModelGateway) -> None:
        self._gateway = gateway

    async def parse(self, text: str) -> RequestParseResult:
        payload = await self._gateway.generate_json(
            system_prompt=(
                "Return only one JSON object with exactly these keys and no markdown: "
                '{"origin":null,"destination":null,"start_date":null,"days":null,'
                '"traveler_ages":null,"maximum_budget":null,"currency":null,'
                '"included_categories":null,"contingency":null,"preferences":[]}. '
                "Extract only explicitly stated values and keep missing values null. Never rename "
                "keys. maximum_budget is the stated total spending ceiling. contingency is an "
                "amount reserved inside that ceiling; never add it to maximum_budget and never "
                "include contingency as a category. included_categories may contain only "
                "transport, lodging, local_transport, activities, meals, insurance, or other, "
                "and must contain exactly the categories explicitly named by the user. Never add "
                "an allowed category that the user did not mention. Do not infer dates, ages, "
                "budget scope, currency, contingency, categories, or preferences."
            ),
            user_prompt=text,
            schema=ExtractedTripRequest.model_json_schema(),
        )
        try:
            extracted = ExtractedTripRequest.model_validate(payload)
        except ValidationError as error:
            raise ValueError("Qwen returned an invalid trip request") from error

        questions = self._questions(extracted)
        if questions:
            return RequestParseResult(request=None, questions=questions)

        return RequestParseResult(request=self._build_request(extracted), questions=())

    @staticmethod
    def _questions(extracted: ExtractedTripRequest) -> tuple[str, ...]:
        questions: list[str] = []
        if not extracted.origin:
            questions.append("Where will the family depart from?")
        if not extracted.destination:
            questions.append("Where does the family want to travel?")
        if extracted.start_date is None:
            questions.append("What date should the trip start?")
        if extracted.days is None:
            questions.append("How many local calendar days should the trip cover?")
        if not extracted.traveler_ages:
            questions.append("What are the ages of every traveler, including each child?")
        if extracted.maximum_budget is None:
            questions.append("What is the maximum trip budget?")
        if extracted.currency is None:
            questions.append("What currency is the trip budget in?")
        if not extracted.included_categories:
            questions.append(
                "Which costs must fit the budget: transport, lodging, local transport, "
                "activities, meals, insurance, or other costs?"
            )
        if extracted.contingency is None:
            questions.append("How much of the budget should be reserved as contingency?")
        return tuple(questions)

    @staticmethod
    def _build_request(extracted: ExtractedTripRequest) -> TripPlanRequest:
        if (
            extracted.origin is None
            or extracted.destination is None
            or extracted.start_date is None
            or extracted.days is None
            or extracted.traveler_ages is None
            or extracted.maximum_budget is None
            or extracted.currency is None
            or extracted.included_categories is None
            or extracted.contingency is None
        ):
            raise RuntimeError("cannot build an incomplete trip request")

        return TripPlanRequest(
            origin=extracted.origin,
            destination=extracted.destination,
            start_date=extracted.start_date,
            days=extracted.days,
            travelers=tuple(Traveler(age=age) for age in extracted.traveler_ages),
            budget=BudgetConstraint(
                maximum=Money(
                    amount=extracted.maximum_budget,
                    currency=extracted.currency,
                ),
                included_categories=extracted.included_categories,
                contingency=Money(
                    amount=extracted.contingency,
                    currency=extracted.currency,
                ),
            ),
            preferences=extracted.preferences or (),
        )