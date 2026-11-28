from pricing_demo.application.ports.pricing_versions import PricingVersions


class DeletePricingVersion:
    """Deletes a pricing version (a draft is discarded) with its periods and finished runs.
    Refused (`RunActive`) while a run of it is queued or running, and (`IsShowcase`) while it
    is the showcase."""

    def __init__(self, pricing: PricingVersions) -> None:
        self._pricing = pricing

    def execute(self, version_id: str) -> None:
        self._pricing.delete(version_id)
