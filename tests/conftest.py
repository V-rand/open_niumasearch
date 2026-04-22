from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--fast",
        action="store_true",
        default=False,
        help="Run the deterministic fast subset for local iteration.",
    )


@pytest.fixture
def is_fast_mode(pytestconfig: pytest.Config) -> bool:
    return bool(pytestconfig.getoption("--fast"))
