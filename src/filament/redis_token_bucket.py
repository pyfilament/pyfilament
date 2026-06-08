import logging

import anyio

from filament.redis_utils import r
from filament.utils import now

logger = logging.getLogger(__name__)


class RedisTokenBucket:
    def __init__(self, name: str, rate_limit: int = 1, capacity: int = 1, redis=None):
        self.name = name
        self.rate_limit = rate_limit
        self.capacity = capacity
        self.last_tokens_key = f'token_bucket:{self.name}:last_tokens'
        self.last_refill_key = f'token_bucket:{self.name}:last_refill'
        self.redis = redis or r

    async def acquire(self, tokens=1):
        while True:
            if tokens > self.capacity:
                raise ValueError(
                    f"Cannot acquire {tokens} tokens, exceeds capacity of {self.capacity} for token bucket '{self.name}'."
                )
            is_allowed = await self._lua_eval(
                self._lua_acquire(),
                keys=[self.last_tokens_key, self.last_refill_key],
                args=[self.rate_limit, self.capacity, tokens, now(places=0)],
            )
            if is_allowed:
                return
            available_tokens = int(await self.redis.get(self.last_tokens_key))
            min_wait_time = max(1, (tokens - available_tokens) / self.rate_limit)
            logger.warning(
                f"Rate limit exceeded for token bucket '{self.name}'. "
                f'Requested {tokens} tokens but only {available_tokens} available. '
                f'Retrying in {min_wait_time} seconds.'
            )
            await anyio.sleep(min_wait_time)

    def _lua_acquire(self):
        return """
        local last_tokens_key = KEYS[1]
        local last_refill_key = KEYS[2]
        local rate_limit = tonumber(ARGV[1])
        local capacity = tonumber(ARGV[2])
        local tokens_requested = tonumber(ARGV[3])
        local now = tonumber(ARGV[4])

        local last_tokens = tonumber(redis.call('GET', last_tokens_key) or capacity)
        local last_refill = tonumber(redis.call('GET', last_refill_key) or now)
        local time_delta = math.max(0, now - last_refill)
        local new_tokens = math.min(capacity, last_tokens + time_delta * rate_limit)
        local is_allowed = new_tokens >= tokens_requested
        if is_allowed then
            new_tokens = new_tokens - tokens_requested
        end

        redis.call('SET', last_tokens_key, new_tokens)
        redis.call('SET', last_refill_key, now)

        return is_allowed
        """

    async def _lua_eval(self, script, keys=[], args=[]):
        return await self.redis.eval(script, len(keys), *keys, *args)
