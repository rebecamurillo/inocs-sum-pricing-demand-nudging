from pricing_demo.domain.package_fingerprint import CHOICE_COEFFICIENT_NAMES
from pricing_demo.infrastructure.pricing_model.choice_coefficients import read_choice_coefficients

SOURCE = """
def solve():
    ASC_PT   = -0.756          # PT alternative-specific constant
    ASC_BIKE = 0.0
    ASC_CAR  = -0.669
    BETA_Cost_BIKE  = 0.689
    BETA_Time_BIKE  = 0.108
    BETA_TR_BIKE    = 0.199
    BETA_Cost_PT    = 0.779
    BETA_Time_PT    = 0.101
    BETA_TR_PT      = 0.208
    BETA_Cost_Car   = 0.474
    BETA_Cost_park  = 0.532
    BETA_Time_Car   = 0.116
    other = 3.0
"""


def test_the_twelve_names_are_read_with_their_signs() -> None:
    found = read_choice_coefficients(SOURCE)

    assert tuple(found) == CHOICE_COEFFICIENT_NAMES
    assert found["ASC_PT"] == -0.756
    assert found["ASC_BIKE"] == 0.0
    assert found["BETA_Time_Car"] == 0.116
    assert None not in found.values()


def test_a_name_that_is_missing_reads_as_none_and_the_others_are_found() -> None:
    found = read_choice_coefficients(SOURCE.replace("BETA_Time_Car   = 0.116", ""))

    assert found["BETA_Time_Car"] is None
    assert found["BETA_Cost_Car"] == 0.474
    assert sum(value is None for value in found.values()) == 1


def test_a_name_assigned_something_that_is_not_a_number_is_missing() -> None:
    source = "ASC_PT = compute()\nASC_CAR = 'x'\nASC_BIKE = True\nBETA_TR_PT = 1 + 2\n"

    found = read_choice_coefficients(source)

    assert all(value is None for value in found.values())


def test_an_integer_constant_reads_as_a_float() -> None:
    assert read_choice_coefficients("ASC_BIKE = 0")["ASC_BIKE"] == 0.0
