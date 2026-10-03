import pytest

from qunxue_api.modules.billing import pricing


def test_sol_price_cache_subsets_and_long_context_boundary():
    book = pricing.PriceBook(credits_per_usd=10000, version="synthetic-contract")
    assert book.cost_pico_usd("gpt-6.1-sol", 1000, 100, 200, 300) == 2770000000
    assert book.credit_numerator(2770000000) == 27700000000000
    assert book.cost_pico_usd("gpt-6.1-sol", 272000, 100, 0, 0) == 545000000000
    assert book.cost_pico_usd("gpt-6.1-sol", 272001, 100, 0, 0) == 1089504000000


def test_luna_alias_requires_explicit_configuration():
    book = pricing.PriceBook(
        credits_per_usd=10000,
        version="synthetic-contract",
        aliases={"openai/gpt-6-luna": "gpt-6-luna"},
    )
    assert book.cost_pico_usd("openai/gpt-6-luna", 1000, 100, 200, 300) == 139500000
    with pytest.raises(pricing.UnknownPrice):
        book.cost_pico_usd("deepseek-flash", 1000, 100, 0, 0)


def test_worst_case_reservation_prices_cache_write_and_long_context():
    book = pricing.PriceBook(credits_per_usd=10000, version="synthetic-contract")
    assert book.maximum_cost("gpt-6.1-sol", 1000, 100) == 3500000000
    assert book.maximum_cost("gpt-6.1-sol", 272001, 100) == 1361505000000


@pytest.mark.parametrize(
    "day,hour,band,cost",
    [
        ("2026-10-02", 1, "off_peak", 330000000),
        ("2026-10-08", 1, "peak", 660000000),
        ("2026-10-08", 4, "off_peak", 330000000),
        ("2026-10-08", 6, "peak", 660000000),
        ("2026-10-08", 10, "off_peak", 330000000),
        ("2026-10-10", 1, "off_peak", 330000000),
    ],
)
def test_deepseek_explicit_dispatch_band_calendar_and_peak_reservation(day, hour, band, cost):
    from datetime import UTC, datetime

    book = pricing.PriceBook(
        credits_per_usd=10000,
        version="synthetic",
        deepseek_time_basis="server_dispatch_at",
        calendar_version="cn-public-holidays-2026-state-council-2025-7-v1",
    )
    locked = book.lock_dispatch(
        "deepseek-flash", datetime.fromisoformat(day).replace(hour=hour, tzinfo=UTC)
    )
    assert locked.reference_band == band
    assert locked.cost_pico_usd("deepseek-flash", 1000, 300, 0, 0) == cost
    assert locked.maximum_cost("deepseek-flash", 1000, 300) == 660000000


def test_deepseek_missing_calendar_year_refuses_dynamic_price():
    from datetime import UTC, datetime

    book = pricing.PriceBook(
        credits_per_usd=10000,
        version="synthetic",
        deepseek_time_basis="server_dispatch_at",
        calendar_version="cn-public-holidays-2026-state-council-2025-7-v1",
    )
    with pytest.raises(pricing.UnknownPrice):
        book.lock_dispatch("deepseek-flash", datetime(2027, 1, 1, tzinfo=UTC))
