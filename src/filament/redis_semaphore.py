import logging
import uuid
from contextlib import asynccontextmanager

import anyio
from redis.asyncio import Redis

from filament.redis_utils import r
from filament.utils import now

logger = logging.getLogger(__name__)

DEFAULT_TTL = 60


class RedisSemaphore:
    def __init__(
        self,
        name: str,
        max_leases: int,
        ttl: int = DEFAULT_TTL,
        redis: Redis = None,
        heartbeat_interval: int = 1,
        heartbeat_ttl: int = 5,
        client_id: str = None,
    ):
        self.redis = redis or r
        self.name = name
        self.max_leases = max_leases
        self.ttl = ttl or DEFAULT_TTL  # must be set
        self.client_id = client_id or str(uuid.uuid4())[-8:]
        self.holders_zset = f'semaphore:holders:{self.name}'
        self.waiters_queue = f'semaphore:waiters:{self.name}'
        self.release_channel = f'semaphore:release:{self.name}'
        self.heartbeat_zset = f'semaphore:heartbeats:{self.name}'
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_ttl = heartbeat_ttl

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.release()

    async def acquire(self, timeout=None):
        logger.debug(f'Acquiring semaphore {self.name} with client_id {self.client_id}')
        with anyio.fail_after(timeout):
            async with anyio.create_task_group() as tg:
                tg.start_soon(self._start_heartbeat)
                # tg.start_soon(self._start_watchdog)
                tg.start_soon(self._acquire, tg)

    async def _start_heartbeat(self):
        while True:
            logger.debug(f'Updating heartbeat for semaphore {self.name} with client_id {self.client_id}')
            # Update the heartbeat in the zset
            await self.redis.zadd(
                self.heartbeat_zset,
                {self.client_id: now(ceil=True) + self.heartbeat_ttl},
            )
            await anyio.sleep(self.heartbeat_interval)

    async def _log_state(self):
        # For debugging purposes, log the current state of the semaphore
        holders = await self.redis.zrange(self.holders_zset, 0, -1, withscores=True)
        waiters = await self.redis.lrange(self.waiters_queue, 0, -1)
        heartbeat = await self.redis.zrange(self.heartbeat_zset, 0, -1, withscores=True)

        if holders:
            logger.debug(f'{self.holders_zset}: {holders}')
        if waiters:
            logger.debug(f'{self.waiters_queue}: {waiters}')
        if heartbeat:
            logger.debug(f'{self.heartbeat_zset}: {heartbeat}')

    async def _acquire(self, tg):
        while True:
            await self._lua_eval(
                self._lua_ensure_in_queue(),
                keys=[self.waiters_queue],
                args=[self.client_id],
            )
            logger.debug(f'Running cleanup script for semaphore {self.name} from client_id {self.client_id}')
            await self._lua_eval(
                self._lua_cleanup_stale_clients(),
                keys=[self.holders_zset, self.waiters_queue, self.heartbeat_zset],
                args=[now()],
            )
            await self._log_state()
            logger.debug(f'Attempting to acquire semaphore {self.name} with client_id {self.client_id}')
            acquired = await self._lua_eval(
                self._lua_acquire_and_dequeue(),
                keys=[self.holders_zset, self.waiters_queue, self.heartbeat_zset],
                args=[self.client_id, self.max_leases, self.ttl, now(ceil=True)],
            )
            logger.debug(
                f'Attempt to acquire semaphore {self.name} with client_id {self.client_id} returned: {acquired}'
            )
            if acquired:
                tg.cancel_scope.cancel()
                return True
            await self._wait_for_release_or_expiry()

    async def _lua_eval(self, script, keys=[], args=[]):
        return await self.redis.eval(script, len(keys), *keys, *args)

    def _lua_cleanup_stale_clients(self):
        return """
        local holders_zset = KEYS[1]
        local waiters_queue = KEYS[2]
        local heartbeat_zset = KEYS[3]
        local now = tonumber(ARGV[1])

        -- TODO: check if self is in first 10 clients in the holders_zset
        -- and if self heartbeat is not yet expired

        redis.call('ZREMRANGEBYSCORE', holders_zset, '-inf', now)
        redis.call('ZREMRANGEBYSCORE', heartbeat_zset, '-inf', now)

        while true do
            local first_client_id = redis.call('LINDEX', waiters_queue, 0)
            if not first_client_id then
                break
            end
            local expiry = redis.call('ZSCORE', heartbeat_zset, first_client_id)
            if not expiry or tonumber(expiry) < now then
                redis.call('LPOP', waiters_queue)
            else
                break
            end
        end
        """

    def _lua_ensure_in_queue(self):
        return """
        local waiters_queue = KEYS[1]
        local client_id = ARGV[1]

        local items = redis.call('LRANGE', waiters_queue, 0, -1)
        for _, val in ipairs(items) do
            if val == client_id then
                return
            end
        end
        redis.call('RPUSH', waiters_queue, client_id)
        """

    def _lua_acquire_and_dequeue(self):
        return """
        local holders_zset = KEYS[1]
        local waiters_queue = KEYS[2]
        local heartbeat_zset = KEYS[3]
        local client_id = ARGV[1]
        local max_leases = tonumber(ARGV[2])
        local ttl = tonumber(ARGV[3])
        local now = tonumber(ARGV[4])

        local front_client_id = redis.call('LINDEX', waiters_queue, 0)
        if front_client_id ~= client_id then
            return 0
        end

        if redis.call('ZCARD', holders_zset) >= max_leases then
            return 0
        end

        redis.call('ZADD', holders_zset, now + ttl, client_id)
        redis.call('LPOP', waiters_queue)
        redis.call('ZREM', heartbeat_zset, client_id)
        return 1
        """

    async def _wait_for_release_or_expiry(self):
        earliest_holders = await self.redis.zrange(self.holders_zset, 0, 0, withscores=True)
        if len(earliest_holders) == 0:
            first_waiter = await self.redis.lindex(self.waiters_queue, 0)
            if first_waiter is None or first_waiter == self.client_id:
                logger.debug(f'No waiters in queue for semaphore {self.name}. Proceeding without waiting.')
                return
            expiry_time = await self.redis.zscore(self.heartbeat_zset, first_waiter)
            if expiry_time is None:
                logger.debug(f'First waiter {first_waiter} has no heartbeat expiry. Proceeding without waiting.')
                return
            # # If there are no holders, wait for the first waiter's heartbeat expiry
            # delay = max(first_waiter_expires - now(), self.heartbeat_interval)
        else:
            earliest_holder = earliest_holders[0]
            _client_id, expiry_time = earliest_holder
        delay = max(expiry_time - now(), self.heartbeat_interval)

        logger.debug(
            f'Waiting for release or expiry for semaphore {self.name} with client_id {self.client_id} for {delay} seconds'
        )
        async with self._get_subscription() as pubsub:
            with anyio.move_on_after(delay):
                while True:
                    message = await pubsub.get_message()
                    if message and message['type'] == 'message':
                        if message['data'] == 'release':
                            logger.debug(
                                f'Received release notification for semaphore {self.name} by client_id {self.client_id}. Proceeding...'
                            )
                            return

    @asynccontextmanager
    async def _get_subscription(self):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self.release_channel)
        try:
            yield pubsub
        finally:
            await pubsub.unsubscribe(self.release_channel)
            await pubsub.close()

    async def release(self):
        logger.debug(f'Releasing semaphore {self.name} for client_id {self.client_id}')
        has_released = await self._lua_eval(self._lua_remove_client(), keys=[self.holders_zset], args=[self.client_id])
        if has_released:
            await self.redis.publish(self.release_channel, 'release')
        else:
            raise RedisSemaphoreException(
                f'Failed to release semaphore {self.name} for client_id {self.client_id}. '
                f'Client may not be a holder or already expired.'
            )

    def _lua_remove_client(self):
        return """
        local holders_zset = KEYS[1]
        local client_id = ARGV[1]

        local score = redis.call('ZSCORE', holders_zset, client_id)
        if not score then
            return 0
        end
        redis.call('ZREM', holders_zset, client_id)
        return 1
        """

    async def extend(self, ttl=None):
        logger.debug(f'Extending semaphore {self.name} for client_id {self.client_id}')
        new_expiry = now(ceil=True) + (ttl or self.ttl)
        # await self.redis.zadd(self.holders_zset, {self.client_id: new_expiry})
        has_extended = await self._lua_eval(
            self._lua_extend_client(),
            keys=[self.holders_zset],
            args=[self.client_id, new_expiry],
        )
        if not has_extended:
            raise RedisSemaphoreException(
                f'Failed to extend semaphore {self.name} for client_id {self.client_id}. '
                f'Client may not be a holder or already expired.'
            )

    def _lua_extend_client(self):
        return """
        local holders_zset = KEYS[1]
        local client_id = ARGV[1]
        local new_expiry = tonumber(ARGV[2])

        local score = redis.call('ZSCORE', holders_zset, client_id)
        if not score then
            return 0
        end
        redis.call('ZADD', holders_zset, new_expiry, client_id)
        return 1
        """


class RedisSemaphoreException(Exception):
    pass
