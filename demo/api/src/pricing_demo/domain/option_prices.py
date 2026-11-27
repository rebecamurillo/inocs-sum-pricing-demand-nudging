"""The price of one option, the single formula behind the traveller simulation and, later,
the traveller view (ARCHITECTURE.md § 6.2).

The package writes `Total Price = p + pt_price` whatever the number of bike legs; what a
two-leg option costs stays provisional (Q-17), so `k x p + fare` is the demonstrator's own
make-up, named here and used everywhere.
"""

from pricing_demo.domain.read_model import RouteMode


def option_price(
    mode: RouteMode,
    bike_legs: int,
    bike_price: float,
    pt_fare_chf: float,
    car_cost_chf: float,
    car_parking_fee_chf: float,
) -> float:
    """PT + bike: `bike_legs x bike_price + fare`; PT alone: `fare`; car: `car cost + parking
    fee`. The arguments a mode does not use are ignored."""
    if mode == "pt_bike":
        return bike_legs * bike_price + pt_fare_chf
    if mode == "pt_only":
        return pt_fare_chf
    return car_cost_chf + car_parking_fee_chf
