"""A local OpenTripPlanner: an HTTP server in the test process that answers the package's
GraphQL queries from `fixtures/otp_answers.json` (the synthetic city's two hubs).

Each (pair, query) answers normally unless a rule says otherwise: fail with a status for the
first `times` attempts (or always), answer no itinerary, or answer only a bike itinerary. Every
request is recorded with its time. The health query (`__typename`) answers 200.
"""

import json
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ANSWERS = Path(__file__).parent / "fixtures" / "otp_answers.json"
PT, CAR = "pt", "car"
BIKE_MODES = {"BICYCLE"}


@dataclass(frozen=True)
class Request:
    pair: str
    query: str
    at: float
    status: int


class OtpStub:
    def __init__(self) -> None:
        self._answers = json.loads(ANSWERS.read_text(encoding="utf-8"))
        self._lock = threading.Lock()
        self._rules: dict[tuple[str, str], dict[str, Any]] = {}
        self._attempts: dict[tuple[str, str], int] = {}
        self.requests: list[Request] = []
        self.queried_at: list[dict[str, Any]] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                status, payload = stub.answer(body)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: object) -> None:
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/otp/gtfs/v1"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def fail(self, pair: str, query: str, status: int, times: int | None = None) -> None:
        """Answer `status` to the first `times` attempts (always when None)."""
        self._rules[(pair, query)] = {"kind": "fail", "status": status, "times": times}

    def empty(self, pair: str, query: str) -> None:
        self._rules[(pair, query)] = {"kind": "empty"}

    def bike_only(self, pair: str) -> None:
        self._rules[(pair, PT)] = {"kind": "bike_only"}

    def attempts(self, pair: str, query: str) -> list[Request]:
        return [item for item in self.requests if (item.pair, item.query) == (pair, query)]

    def answer(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        variables = body.get("variables")
        if not variables:
            return 200, {"data": {"__typename": "QueryType"}}
        pair = f"{self._hub_at(variables['from'])}|{self._hub_at(variables['to'])}"
        modes = [item["mode"] for item in variables["transportModes"]]
        query = CAR if modes == ["CAR"] else PT
        with self._lock:
            key = (pair, query)
            self._attempts[key] = self._attempts.get(key, 0) + 1
            rule = self._rules.get(key, {})
            status = 200
            if rule.get("kind") == "fail" and (
                rule["times"] is None or self._attempts[key] <= rule["times"]
            ):
                status = rule["status"]
            self.requests.append(Request(pair, query, time.monotonic(), status))
            self.queried_at.append({"date": variables["date"], "time": variables["time"]})
        if status != 200:
            return status, {"errors": [{"message": "scripted failure"}]}
        itineraries = self._answers["pairs"][pair][query]["itineraries"]
        if rule.get("kind") == "empty":
            itineraries = []
        if rule.get("kind") == "bike_only":
            itineraries = [
                item for item in itineraries if {leg["mode"] for leg in item["legs"]} <= BIKE_MODES
            ]
        return 200, {"data": {"plan": {"itineraries": itineraries}}}

    def _hub_at(self, place: dict[str, float]) -> str:
        for hub, (lat, lon) in self._answers["hubs"].items():
            if abs(lat - place["lat"]) < 1e-6 and abs(lon - place["lon"]) < 1e-6:
                return str(hub)
        raise AssertionError(f"no hub at {place}")
