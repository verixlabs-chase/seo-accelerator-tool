from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TokenBucketState:
    capacity: int
    refill_rate_per_second: float
    tokens: float
    last_refill_epoch: int


class TokenBucket:
    def __init__(self, state: TokenBucketState) -> None:
        self.state = state

    def refill(self, *, now_epoch: int) -> None:
        if now_epoch <= self.state.last_refill_epoch:
            return
        elapsed = now_epoch - self.state.last_refill_epoch
        refill_amount = elapsed * self.state.refill_rate_per_second
        self.state.tokens = min(float(self.state.capacity), self.state.tokens + refill_amount)
        self.state.last_refill_epoch = now_epoch

    def try_consume(self, *, now_epoch: int, amount: float = 1.0) -> bool:
        if amount <= 0:
            raise ValueError("amount must be greater than zero")
        self.refill(now_epoch=now_epoch)
        if self.state.tokens < amount:
            return False
        self.state.tokens -= amount
        return True


def emit_token_bucket_metric_stub(*, tenant_id: str, queue_name: str, allowed: bool) -> None:
    _ = (tenant_id, queue_name, allowed)
