from pricing_demo.domain.errors import DomainError


class InvalidProbeSet(DomainError):
    pass


class ComponentNotControllable(DomainError):
    pass
