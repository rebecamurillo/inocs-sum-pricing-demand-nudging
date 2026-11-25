import pytest

from tests.support.database import TEST_DATABASE_ENV, require_database_url


def test_the_url_comes_from_the_test_variable() -> None:
    assert require_database_url({TEST_DATABASE_ENV: "postgresql://t"}) == "postgresql://t"


@pytest.mark.parametrize(
    "environ",
    [
        {},
        {TEST_DATABASE_ENV: ""},
        {"PRICING_DEMO_DATABASE_URL": "postgresql://the-application-database"},
    ],
)
def test_without_the_test_variable_the_run_fails_and_never_uses_the_application_url(
    environ: dict[str, str],
) -> None:
    with pytest.raises(pytest.fail.Exception, match=f"{TEST_DATABASE_ENV} is not set"):
        require_database_url(environ)
