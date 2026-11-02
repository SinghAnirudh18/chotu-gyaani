"""Reminder delivery. No real WhatsApp/SMS provider is chosen yet, so the stub
records the attempt and never claims delivery."""
from dataclasses import dataclass


@dataclass
class DeliveryResult:
    delivered: bool
    error: str | None


class StubDelivery:
    name = "stub"

    async def send(self, channel: str, to: str | None, message: str) -> DeliveryResult:
        return DeliveryResult(delivered=False, error="delivery_provider_not_configured")


def get_delivery() -> StubDelivery:
    return StubDelivery()
