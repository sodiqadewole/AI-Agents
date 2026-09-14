# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false

from __future__ import annotations

from datetime import timedelta
from typing import NotRequired, Required, TypedDict

from langgraph.graph import END, START, StateGraph

from travel_agent.budget import verify_budget
from travel_agent.domain import (
    BudgetVerification,
    CostItem,
    DailyPlan,
    Offer,
    TripCostLedger,
    TripPlan,
    TripPlanRequest,
)
from travel_agent.inventory import InventoryGateway


class PlannerState(TypedDict):
    request: Required[TripPlanRequest]
    offers: NotRequired[tuple[Offer, ...]]
    plan: NotRequired[TripPlan]
    verification: NotRequired[BudgetVerification]


class TravelPlanner:
    def __init__(self, inventory: InventoryGateway) -> None:
        self._inventory = inventory
        graph = StateGraph(PlannerState)
        graph.add_node("search", self._search)
        graph.add_node("compose", self._compose)
        graph.add_node("verify", self._verify)
        graph.add_edge(START, "search")
        graph.add_edge("search", "compose")
        graph.add_edge("compose", "verify")
        graph.add_edge("verify", END)
        self._graph = graph.compile()

    async def plan(self, request: TripPlanRequest) -> tuple[TripPlan, BudgetVerification]:
        state = await self._graph.ainvoke({"request": request})
        plan = state.get("plan")
        verification = state.get("verification")
        if plan is None or verification is None:
            raise RuntimeError("planner graph completed without a verified plan")
        return plan, verification

    async def _search(self, state: PlannerState) -> PlannerState:
        return {
            "request": state["request"],
            "offers": await self._inventory.search(state["request"]),
        }

    @staticmethod
    def _compose(state: PlannerState) -> PlannerState:
        request = state["request"]
        required = request.budget.included_categories
        selected: list[Offer] = []
        offers = state.get("offers")
        if offers is None:
            raise RuntimeError("compose step requires search offers")

        for category in sorted(required, key=lambda item: item.value):
            candidates = [offer for offer in offers if offer.category == category]
            if candidates:
                selected.append(min(candidates, key=lambda offer: offer.price.amount))

        selected_categories = {offer.category for offer in selected}
        missing = required - selected_categories
        items = tuple(
            CostItem(
                category=offer.category,
                description=offer.title,
                amount=offer.price,
                offer_id=offer.offer_id,
                estimated=offer.category.value == "meals",
            )
            for offer in selected
        )
        ledger = TripCostLedger(
            items=items,
            contingency=request.budget.contingency,
            unknown_required_categories=missing,
        )
        days = tuple(
            DailyPlan(
                local_date=request.start_date + timedelta(days=offset),
                title=f"Day {offset + 1} in {request.destination}",
                activities=("Family activity planning placeholder",),
            )
            for offset in range(request.days)
        )
        return {
            "request": request,
            "plan": TripPlan(
                request=request,
                days=days,
                selected_offers=tuple(selected),
                ledger=ledger,
            )
        }

    @staticmethod
    def _verify(state: PlannerState) -> PlannerState:
        plan = state.get("plan")
        if plan is None:
            raise RuntimeError("verify step requires a composed plan")
        return {
            "request": state["request"],
            "verification": verify_budget(state["request"], plan.ledger),
        }