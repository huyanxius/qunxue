"""Versioned USD reference rates, exact integer arithmetic and explicit aliases."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from zoneinfo import ZoneInfo

from qunxue_api.modules.billing.domain import BillingFailure

PICO_USD = 10**12


class UnknownPrice(BillingFailure, ValueError):
    code = "billing_price_unknown"
    pass


@dataclass(frozen=True)
class Tariff:
    # microUSD per million tokens = picoUSD per token, exactly.
    input: int
    cache_read: int
    cache_write: int
    output: int
    long_threshold: int | None = 272000
    reservation_rates: tuple[int, int, int, int] | None = None
    currency: str = "USD"
    service_tier: str = "standard"

    def rates(self, input_tokens: int) -> tuple[int, int, int, int]:
        if self.long_threshold is not None and input_tokens > self.long_threshold:
            return self.input * 2, self.cache_read * 2, self.cache_write * 2, self.output * 3 // 2
        return self.input, self.cache_read, self.cache_write, self.output


STANDARD_TARIFFS = {
    "gpt-6.1-sol": Tariff(2000000, 100000, 2500000, 10000000),
    "gpt-6-luna": Tariff(100000, 10000, 125000, 500000),
}


@dataclass(frozen=True)
class PriceBook:
    credits_per_usd: int
    version: str
    aliases: Mapping[str, str] = field(default_factory=dict)
    usage_policies: Mapping[str, str] = field(default_factory=dict)
    tariffs: Mapping[str, Tariff] = field(default_factory=lambda: dict(STANDARD_TARIFFS))

    deepseek_time_basis: str | None = None
    calendar_version: str | None = None
    reference_band: str | None = None
    dispatch_at: str | None = None

    def lock_dispatch(self, model: str, instant: datetime):
        if self.aliases.get(model, model) != "deepseek-flash":
            return self
        if (
            self.deepseek_time_basis != "server_dispatch_at"
            or self.calendar_version != "cn-public-holidays-2026-state-council-2025-7-v1"
        ):
            raise UnknownPrice("DeepSeek reference-time policy/calendar must be explicitly enabled")
        local = instant.astimezone(ZoneInfo("Asia/Shanghai"))
        if local.year != 2026:
            raise UnknownPrice("DeepSeek calendar year is not configured")
        day = local.date().isoformat()
        holiday = any(
            start <= day <= end
            for start, end in (
                ("2026-01-01", "2026-01-03"),
                ("2026-02-15", "2026-02-23"),
                ("2026-04-04", "2026-04-06"),
                ("2026-05-01", "2026-05-05"),
                ("2026-06-19", "2026-06-21"),
                ("2026-09-25", "2026-09-27"),
                ("2026-10-01", "2026-10-07"),
            )
        )
        peak = (
            local.weekday() < 5 and not holiday and (9 <= local.hour < 12 or 14 <= local.hour < 18)
        )
        tariff = (
            Tariff(300000, 6000, 0, 1200000, long_threshold=None)
            if peak
            else Tariff(150000, 3000, 0, 600000, long_threshold=None)
        )
        tariff = replace(tariff, reservation_rates=(300000, 6000, 0, 1200000))
        return replace(
            self,
            tariffs={**self.tariffs, "deepseek-flash": tariff},
            reference_band="peak" if peak else "off_peak",
            dispatch_at=instant.isoformat(),
        )

    def __post_init__(self):
        if type(self.credits_per_usd) is not int or self.credits_per_usd <= 0 or not self.version:
            raise ValueError("billing conversion and version must be explicitly configured")
        if any(
            policy != "omitted_cache_subsets_are_zero" for policy in self.usage_policies.values()
        ):
            raise ValueError("unsupported provider usage policy")
        for tariff in self.tariffs.values():
            if (
                tariff.currency != "USD"
                or any(
                    type(n) is not int or n < 0
                    for n in (
                        tariff.input,
                        tariff.cache_read,
                        tariff.cache_write,
                        tariff.output,
                    )
                )
                or tariff.output % 2
            ):
                raise ValueError("tariff must contain exact nonnegative USD integer rates")

    def tariff(self, model: str) -> Tariff:
        canonical = self.aliases.get(model, model)
        try:
            return self.tariffs[canonical]
        except KeyError:
            raise UnknownPrice("model has no configured billing tariff") from None

    def cost_pico_usd(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> int:
        counts = input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
        if any(type(n) is not int or n < 0 for n in counts):
            raise ValueError("invalid token counts")
        ordinary = input_tokens - cache_read_tokens - cache_write_tokens
        if ordinary < 0:
            raise ValueError("cached token subsets exceed input")
        u, c, w, o = self.tariff(model).rates(input_tokens)
        return ordinary * u + cache_read_tokens * c + cache_write_tokens * w + output_tokens * o

    def maximum_cost(self, model: str, input_limit: int, output_limit: int) -> int:
        if (
            type(input_limit) is not int
            or type(output_limit) is not int
            or min(input_limit, output_limit) < 0
        ):
            raise ValueError("invalid request limits")
        tariff = self.tariff(model)
        u, c, w, o = tariff.reservation_rates or tariff.rates(input_limit)
        return input_limit * max(u, c, w) + output_limit * o

    def credit_numerator(self, cost_pico_usd: int) -> int:
        return cost_pico_usd * self.credits_per_usd
