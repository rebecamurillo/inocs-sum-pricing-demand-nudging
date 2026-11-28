"""A number shown on a screen, with the unit it is in and where it comes from."""

from dataclasses import dataclass
from typing import Literal

NumberSource = Literal["model", "package_summary", "input", "trip_planner", "derived", "simulation"]
NumberGroup = Literal["headline", "advanced"]


@dataclass(frozen=True)
class Number:
    """`source` says who produced it: `input` for what the build reads from the city data,
    `model` for what the pricing model outputs, `derived` for what the demonstrator computes."""

    value: float | int
    unit: str
    source: NumberSource
    group: NumberGroup
