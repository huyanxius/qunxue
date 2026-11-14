"""Qunxue's product tariff and model spending limits."""

from collections.abc import Mapping
from urllib.parse import urlsplit

from qunxue_api.adapters.model.routing import ModelEndpoint
from qunxue_api.modules.billing import POINTS_PER_CNY, STANDARD_TARIFFS, PriceBook, Tariff

PRICE_VERSION = "qunxue-2026-11"
# Fixed conversion for product credits. Supplier reconciliation uses its own invoices.
REFERENCE_CNY_PER_USD = 7
# Per-attempt headroom covers large contexts. The operation limit bounds agent tools
# and retries together, and the daily limit caps aggregate reference spend.
ATTEMPT_USD_MICRO = 500_000
OPERATION_USD_MICRO = 1_000_000
DAILY_USD_MICRO = 10_000_000
PICO_PER_MICRO = 10**6

MODEL_ALIASES = {
    "gpt-5.6": "gpt-5.6-sol",
    "openai/gpt-5.6-sol": "gpt-5.6-sol",
    "deepseek-v4-flash": "deepseek-flash",
    "deepseek-v4.1-flash": "deepseek-flash",
    "deepseek-v4.1-flash-1017": "deepseek-flash",
}
# Stable product rates based on published standard rates. Charge DeepSeek at the
# reference peak rate throughout the day so calendar updates can't block a chat.
PRODUCT_TARIFFS = {
    **STANDARD_TARIFFS,
    "gpt-5.6-sol": Tariff(4_000_000, 400_000, 5_000_000, 20_000_000),
    "deepseek-flash": Tariff(300_000, 6_000, 0, 1_200_000, long_threshold=None),
}


def product_price_book(
    endpoints: tuple[ModelEndpoint, ...],
    *,
    model_aliases: Mapping[str, str],
    usage_policy_overrides: Mapping[str, str],
) -> PriceBook:
    aliases = {**MODEL_ALIASES, **model_aliases}
    # For standard Chat Completions, input without a reported cache breakdown
    # is treated as ordinary input for the product charge.
    usage_policies = {
        f"{urlsplit(endpoint.base_url).hostname}:{endpoint.model}": "omitted_cache_subsets_are_zero"
        for endpoint in endpoints
        if aliases.get(endpoint.model, endpoint.model) != "deepseek-flash"
    }
    return PriceBook(
        version=PRICE_VERSION,
        credits_per_usd=POINTS_PER_CNY * REFERENCE_CNY_PER_USD,
        tariffs=PRODUCT_TARIFFS,
        aliases=aliases,
        usage_policies={**usage_policies, **usage_policy_overrides},
    )
