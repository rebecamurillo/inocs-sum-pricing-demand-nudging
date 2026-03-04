# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


GRAPHQL_QUERY = """query trip(
        $from: InputCoordinates!,
        $to: InputCoordinates!,
        $date: String!,
        $time: String!,
        $maxTransfers: Int,
    $bikeSpeed: Float, $walkSpeed: Float,
        $arriveBy: Boolean,
        $numItineraries: Int,
        $transportModes: [TransportMode]
  ) {
    plan(
        from: $from,
        to: $to,
        date: $date,
        time: $time,
        maxTransfers: $maxTransfers,
        bikeSpeed: $bikeSpeed,
        walkSpeed: $walkSpeed,
        arriveBy: $arriveBy,
        numItineraries: $numItineraries,
        transportModes: $transportModes
  ) {
        itineraries {
            legs {
                mode
                duration
                distance
                route { shortName }
                from { name lat lon }
                to { name lat lon }
                rentedBike
            }
        }
  }
}"""


class OTPUnavailableError(RuntimeError):
    pass


@dataclass
class OTPClient:
    url: str

    def __post_init__(self) -> None:
        self.session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=100,
            pool_maxsize=100,
            max_retries=Retry(total=2, backoff_factor=0.1),
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def health_check(self) -> bool:
        try:
            response = self.session.post(self.url, json={"query": "query { __typename }"}, timeout=10)
            return response.status_code < 500
        except requests.RequestException:
            return False

    def ensure_available(self) -> None:
        if not self.health_check():
            raise OTPUnavailableError(f"OTP endpoint is not available: {self.url}")

    def _build_transport_modes(self, otp_params: dict[str, Any]) -> list[dict[str, str]]:
        if transport_modes := otp_params.get("transportModes"):
            return transport_modes

        return [
            {"mode": "BICYCLE", "qualifier": "RENT"},
            {"mode": "BUS"},
            {"mode": "TRAM"},
            {"mode": "WALK"},
        ]

    def _build_variables(self, origin: dict[str, float], destination: dict[str, float], date_time: str, otp_params: dict[str, Any]) -> dict[str, Any]:
        dt = datetime.fromisoformat(date_time.replace("Z", "+00:00"))
        return {
            "from": {"lat": origin["lat"], "lon": origin["lon"]},
            "to": {"lat": destination["lat"], "lon": destination["lon"]},
            "date": dt.strftime("%Y-%m-%d"),
            "time": dt.strftime("%H:%M:%S"),
            "maxTransfers": otp_params.get("maxTransfers"),
            "bikeSpeed": otp_params.get("bikeSpeed"),
            "walkSpeed": otp_params.get("walkSpeed"),
            "arriveBy": otp_params.get("arriveBy"),
            "numItineraries": otp_params.get("numItineraries", 10),
            "transportModes": self._build_transport_modes(otp_params),
        }

    def _normalize_itineraries(self, itineraries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        patterns = []
        for itinerary in itineraries:
            mapped_legs = []
            for leg in itinerary.get("legs", []):
                mode = leg.get("mode", "")
                normalized_mode = "FOOT" if mode.upper() == "WALK" else mode
                route = leg.get("route") or {}
                from_place = leg.get("from") or {}
                to_place = leg.get("to") or {}
                mapped_legs.append(
                    {
                        "mode": normalized_mode,
                        "duration": leg.get("duration", 0.0),
                        "distance": leg.get("distance", 0.0),
                        "line": {"publicCode": route.get("shortName", "")},
                        "fromPlace": {
                            "name": from_place.get("name", ""),
                            "lat": from_place.get("lat"),
                            "lon": from_place.get("lon"),
                        },
                        "toPlace": {
                            "name": to_place.get("name", ""),
                            "lat": to_place.get("lat"),
                            "lon": to_place.get("lon"),
                        },
                        "rentedBike": leg.get("rentedBike", False),
                    }
                )
            patterns.append({"legs": mapped_legs})
        return patterns

    def query_trip(self, origin: dict[str, float], destination: dict[str, float], date_time: str, otp_params: dict[str, Any]) -> list[dict[str, Any]]:
        variables = self._build_variables(origin, destination, date_time, otp_params)
        logger.debug("OTP query variables: %s", variables)
        response = self.session.post(
            self.url,
            json={"query": GRAPHQL_QUERY, "variables": variables},
            timeout=60,
        )
        logger.debug("OTP HTTP status: %s", response.status_code)
        response.raise_for_status()
        payload = response.json()
        if errors := payload.get("errors"):
            logger.warning("OTP GraphQL errors: %s", errors)
        data = payload.get("data")
        if data is None:
            logger.warning("OTP response has no 'data' field. Full payload: %s", payload)
            return []
        plan = data.get("plan")
        if plan is None:
            logger.warning("OTP response 'data.plan' is null. Full payload: %s", payload)
            return []

        itineraries = plan.get("itineraries", [])
        patterns = self._normalize_itineraries(itineraries)

        logger.debug("OTP raw itineraries count: %d", len(itineraries))
        logger.debug("OTP normalized tripPatterns count: %d", len(patterns))
        return patterns

    def query_car_trip(self, origin: dict[str, float], destination: dict[str, float], date_time: str, otp_params: dict[str, Any]) -> list[dict[str, Any]]:
        car_params = dict(otp_params)
        car_params["transportModes"] = [{"mode": "CAR"}]
        variables = self._build_variables(origin, destination, date_time, car_params)
        logger.debug("OTP CAR query variables: %s", variables)

        response = self.session.post(
            self.url,
            json={"query": GRAPHQL_QUERY, "variables": variables},
            timeout=60,
        )
        logger.debug("OTP CAR HTTP status: %s", response.status_code)
        response.raise_for_status()

        payload = response.json()
        if errors := payload.get("errors"):
            logger.warning("OTP CAR GraphQL errors: %s", errors)
        data = payload.get("data")
        if data is None:
            logger.warning("OTP CAR response has no 'data' field. Full payload: %s", payload)
            return []

        plan = data.get("plan")
        if plan is None:
            logger.warning("OTP CAR response 'data.plan' is null. Full payload: %s", payload)
            return []

        itineraries = plan.get("itineraries", [])
        patterns = self._normalize_itineraries(itineraries)

        logger.debug("OTP CAR raw itineraries count: %d", len(itineraries))
        logger.debug("OTP CAR normalized tripPatterns count: %d", len(patterns))
        return patterns
