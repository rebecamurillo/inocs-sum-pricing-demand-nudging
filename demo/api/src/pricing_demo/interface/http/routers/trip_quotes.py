from typing import Annotated, Any

from fastapi import APIRouter, Query

from pricing_demo.application.use_cases.quote_trip import QuoteTrip
from pricing_demo.interface.http.schemas import ProblemDetails, TripQuoteResponse

Responses = dict[int | str, dict[str, Any]]


def _problem(description: str) -> dict[str, Any]:
    return {"model": ProblemDetails, "description": description}


def build_trip_quotes_router(quote: QuoteTrip) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["trip-quotes"])

    @router.get(
        "/trip-quotes",
        operation_id="quoteTrip",
        summary="A trip between two points, quoted hub to hub from stored data",
        description=(
            "Reads the stored build and result only: no trip planner is called. Without a "
            "price the answer is 200 with the reason in `status`."
        ),
        response_model=TripQuoteResponse,
        responses={
            404: _problem(
                "`pricing_version_not_found`, or `no_result`: the version has no finished result"
            ),
            422: _problem(
                "`no_point`, `malformed_point`, `period_not_priced`, or the request is not valid"
            ),
            500: _problem("Unexpected error"),
        },
    )
    def quote_route(
        pricing_version: Annotated[str, Query(description="The pricing version's id.")],
        period: Annotated[
            str | None,
            Query(description="The period's key; the version's only period when absent."),
        ] = None,
        from_point: Annotated[
            str | None, Query(alias="from", description="Point A as `lat,lon`.")
        ] = None,
        to_point: Annotated[
            str | None, Query(alias="to", description="Point B as `lat,lon`.")
        ] = None,
    ) -> TripQuoteResponse:
        return TripQuoteResponse.from_domain(
            quote.execute(pricing_version, period, from_point, to_point)
        )

    return router
