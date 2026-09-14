import argparse
import asyncio
from datetime import date
from decimal import Decimal

import httpx

from travel_agent.domain import BudgetConstraint, CostCategory, Money, Traveler, TripPlanRequest
from travel_agent.inventory import FakeInventory
from travel_agent.model_gateway import OllamaGateway
from travel_agent.planner import TravelPlanner
from travel_agent.request_parser import NaturalLanguageRequestParser


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan a bounded five-day family trip")
    parser.add_argument("--origin", default="Chicago")
    parser.add_argument("--destination", default="Washington, DC")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--budget", type=Decimal, default=Decimal("4000"))
    parser.add_argument("--currency", default="USD")
    parser.add_argument(
        "--request",
        help="Natural-language trip request to extract with the configured Ollama model",
    )
    parser.add_argument("--use-ollama", action="store_true")
    parser.add_argument("--ollama-model", default="qwen3.5:latest")
    return parser


async def _run(args: argparse.Namespace) -> int:
    gateway = OllamaGateway(model=args.ollama_model)
    if args.request:
        parsed = await NaturalLanguageRequestParser(gateway).parse(args.request)
        if parsed.request is None:
            print("More information is required:")
            for number, question in enumerate(parsed.questions, start=1):
                print(f"{number}. {question}")
            return 3
        request = parsed.request
    else:
        request = _request_from_flags(args)

    plan, verification = await TravelPlanner(FakeInventory()).plan(request)
    print(plan.model_dump_json(indent=2))
    print(f"\nBudget accepted: {verification.accepted}")
    print(f"Total: {verification.total.amount} {verification.total.currency}")
    print(f"Remaining: {verification.remaining.amount} {verification.remaining.currency}")

    if args.use_ollama:
        explanation = await gateway.explain(plan.model_dump_json(indent=2))
        print(f"\nQwen explanation:\n{explanation}")

    return 0 if verification.accepted else 2


def _request_from_flags(args: argparse.Namespace) -> TripPlanRequest:
    currency = str(args.currency).upper()
    return TripPlanRequest(
        origin=args.origin,
        destination=args.destination,
        start_date=args.start_date,
        days=5,
        travelers=(Traveler(age=38), Traveler(age=37), Traveler(age=10), Traveler(age=7)),
        budget=BudgetConstraint(
            maximum=Money(amount=args.budget, currency=currency),
            included_categories=frozenset(
                {
                    CostCategory.TRANSPORT,
                    CostCategory.LODGING,
                    CostCategory.LOCAL_TRANSPORT,
                    CostCategory.ACTIVITIES,
                    CostCategory.MEALS,
                }
            ),
            contingency=Money(amount=Decimal("200"), currency=currency),
        ),
        preferences=("family-friendly", "moderate pace"),
    )


def main() -> None:
    args = _parser().parse_args()
    try:
        status = asyncio.run(_run(args))
    except httpx.ConnectError:
        print("Cannot connect to Ollama at http://localhost:11434. Start Ollama and retry.")
        status = 4
    except httpx.TimeoutException:
        print("Ollama did not respond within 180 seconds. Check local model resources and retry.")
        status = 4
    except ValueError as error:
        print(f"Ollama returned an invalid travel request: {error}")
        status = 4
    raise SystemExit(status)


if __name__ == "__main__":
    main()