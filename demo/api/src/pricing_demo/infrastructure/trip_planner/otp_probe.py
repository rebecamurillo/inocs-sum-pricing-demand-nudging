import httpx

from pricing_demo.domain.system_status import ComponentName, ComponentStatus

TIMEOUT_S = 2


class OtpProbe:
    """OpenTripPlanner answers a GraphQL request."""

    component = ComponentName.TRIP_PLANNER

    def __init__(self, url: str, transport: httpx.BaseTransport | None = None) -> None:
        self._url = url
        self._transport = transport

    def check(self) -> ComponentStatus:
        try:
            with httpx.Client(timeout=TIMEOUT_S, transport=self._transport) as client:
                response = client.post(self._url, json={"query": "{ __typename }"})
        except httpx.TimeoutException:
            return ComponentStatus.unavailable(
                self.component, f"No answer from {self._url} within {TIMEOUT_S} s."
            )
        except httpx.HTTPError as error:
            return ComponentStatus.unavailable(
                self.component, f"{self._url} is not reachable: {error}"
            )
        if response.status_code != httpx.codes.OK:
            return ComponentStatus.unavailable(
                self.component, f"{self._url} answered HTTP {response.status_code}."
            )
        return ComponentStatus.ready(self.component)
