from pricing_demo.domain.option_prices import option_price


def test_pt_bike_is_legs_times_bike_price_plus_fare() -> None:
    assert option_price("pt_bike", 1, 2.0, 3.0, 0.0, 0.0) == 5.0


def test_two_leg_pt_bike_pays_the_bike_price_twice() -> None:
    assert option_price("pt_bike", 2, 2.0, 3.0, 0.0, 0.0) == 7.0


def test_flat_case_is_legs_times_flat_price_plus_fare() -> None:
    assert option_price("pt_bike", 2, 1.5, 2.5, 0.0, 0.0) == 5.5


def test_pt_only_is_the_fare() -> None:
    assert option_price("pt_only", 0, 9.0, 3.0, 8.0, 7.0) == 3.0


def test_car_is_cost_plus_parking_fee() -> None:
    assert option_price("car", 0, 9.0, 3.0, 8.0, 4.0) == 12.0
