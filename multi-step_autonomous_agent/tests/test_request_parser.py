import asyncio
from datetime import date
from decimal import Decimal

from travel_agent.request_parser import NaturalLanguageRequestParser


class FakeStructuredGateway:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, object],
    ) -> dict[str, object]:
        assert "explicitly stated" in system_prompt
        assert "never add it to maximum_budget" in system_prompt
        assert "exactly the categories explicitly named" in system_prompt
        assert user_prompt
        assert schema["type"] == "object"
        return self._payload


def test_builds_validated_request_from_complete_extraction() -> None:
    parser = NaturalLanguageRequestParser(
        FakeStructuredGateway(
            {
                "origin": "Chicago",
                "destination": "Washington, DC",
                "start_date": "2026-10-05",
                "days": 5,
                "traveler_ages": [38, 37, 10, 7],
                "maximum_budget": "4000",
                "currency": "USD",
                "included_categories": [
                    "transport",
                    "lodging",
                    "local_transport",
                    "activities",
                    "meals",
                ],
                "contingency": "200",
                "preferences": ["family-friendly", "moderate pace"],
            }
        )
    )

    result = asyncio.run(parser.parse("complete family trip request"))

    assert result.questions == ()
    assert result.request is not None
    assert result.request.start_date == date(2026, 10, 5)
    assert result.request.days == 5
    assert result.request.budget.maximum.amount == Decimal("4000")
    assert tuple(traveler.age for traveler in result.request.travelers) == (38, 37, 10, 7)


def test_returns_questions_instead_of_inventing_missing_constraints() -> None:
    parser = NaturalLanguageRequestParser(
        FakeStructuredGateway(
            {
                "origin": "Chicago",
                "destination": "Washington, DC",
                "days": 5,
                "maximum_budget": "4000",
                "currency": "USD",
            }
        )
    )

    result = asyncio.run(parser.parse("Plan a five-day family trip under USD 4,000"))

    assert result.request is None
    assert result.questions == (
        "What date should the trip start?",
        "What are the ages of every traveler, including each child?",
        (
            "Which costs must fit the budget: transport, lodging, local transport, "
            "activities, meals, insurance, or other costs?"
        ),
        "How much of the budget should be reserved as contingency?",
    )