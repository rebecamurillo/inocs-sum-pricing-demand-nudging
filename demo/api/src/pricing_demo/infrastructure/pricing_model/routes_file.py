"""The routes file in a fixed order (model-notes entry 10). Pure: the package is not imported."""

from collections.abc import Mapping
from typing import Any


def sorted_routes(payload: Mapping[str, Any]) -> dict[str, Any]:
    """A copy of the payload with `od_results` sorted by (`from_id`, `to_id`): the package
    writes them in the order its threads finished, which changes the travellers drawn from them
    for the same seed."""
    result = dict(payload)
    result["od_results"] = sorted(
        payload.get("od_results", []), key=lambda item: (item["from_id"], item["to_id"])
    )
    return result
