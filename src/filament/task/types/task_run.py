from typing import TYPE_CHECKING
import asyncio
import functools
import inspect
import logging
import math
import random
from contextlib import asynccontextmanager, contextmanager
from uuid import uuid4

import anyio
from anyio.abc import TaskGroup
from beartype.typing import Optional, Union
from pydantic import Field

from filament.logic.cache_utils import (
    cache_get,
    cache_has_key,
    cache_set,
)
from filament.task.constants import TaskState
from filament.redis.logging_handler import JSONFormatter, RedisHandler
from filament.redis.semaphore import RedisSemaphore
from filament.redis.token_bucket import RedisTokenBucket
from filament.task.state.task_state import (
    is_canceled,
    set_heartbeat,
    set_task_result,
    transition_state,
)
from filament.logic.utils import get_function_type
from filament.logic.call_stack import pop_task_run, push_task_run
from filament.task.types.base import FilamentBaseModel
from filament.task.types.task_config import FilamentTaskConfig
from filament.task.constants import DEFAULT_HEARTBEAT_INTERVAL, DEFAULT_MONITOR_INTERVAL
from filament.task.state.task_run_state import initialize_task_run_state

if TYPE_CHECKING:
    from filament.task.types.task_type import FilamentTaskType


class FilamentTaskRun(FilamentBaseModel):
    type: FilamentTaskType
    config: FilamentTaskConfig = Field(default_factory=lambda: FilamentTaskConfig())
    uuid: str
    task_args: tuple = Field(default=())
    task_kwargs: dict = Field(default={})
    name: str
    worker_id: str | None = None

    def __init__(
        self,
        type: FilamentTaskType,
        task_args,
        task_kwargs,
        name=None,
        uuid=None,
        config: Optional[Union[FilamentTaskConfig, dict]] = None,
        worker_id: str | None = None,
    ):
        if config is not None:
            if isinstance(config, dict):
                config = FilamentTaskConfig(**config)
            else:
                config = config.model_copy()
            for config_name in FilamentTaskConfig.model_fields.keys():
                if config_name in task_kwargs:
                    config_value = task_kwargs[config_name]
                    signature = inspect.signature(type._func)
                    if config_name not in signature.parameters.keys():
                        task_kwargs.pop(config_name)
                    setattr(config, config_name, config_value)

        if uuid is None:
            uuid = str(uuid4())

        if name is None:
            name = f'{type.name}({uuid})'

        super().__init__(
            name=name,
            type=type,
            uuid=uuid,
            task_args=task_args,
            task_kwargs=task_kwargs,
            config=config,
            worker_id=worker_id,
        )

    def __hash__(self):
        return self.uuid.__hash__()

    def model_post_init(self, __context):
        self._try_index = None
        self._result = None
        self._exception = None
        self._result_send, self._result_receive = anyio.create_memory_object_stream(math.inf)
        self._done_event = anyio.Event()
        self._task = None
        logger_name = f'{self.type.func_address}:{self.uuid}'
        self._logger = logging.getLogger(logger_name)
        _handler = RedisHandler()
        _handler.setFormatter(JSONFormatter())
        self._logger.addHandler(_handler)
        # a little scary to run the task on init, in case there's a concurrent worker
        if self.config.start_immediately:
            self.start()

    def start(self):
        if self._task:
            return self._task
        self._task = asyncio.create_task(self.call())
        return self._task

    async def _start_heartbeat(self) -> None:
        while not self._done_event.is_set():
            await set_heartbeat(self.uuid)
            await anyio.sleep(self.config.heartbeat_interval or DEFAULT_HEARTBEAT_INTERVAL)

    async def _start_cancel_monitor(self, task_group: TaskGroup) -> None:
        while not self._done_event.is_set():
            if await is_canceled(self.uuid):
                task_group.cancel_scope.cancel()
            await anyio.sleep(self.config.monitor_interval or DEFAULT_MONITOR_INTERVAL)

    @contextmanager
    def _register_frame(self):
        push_task_run(self)
        try:
            yield
        finally:
            pop_task_run()

    @asynccontextmanager
    async def _acquire_token_bucket(self):
        if self.config.rate_limit is None:
            yield
            return
        bucket = RedisTokenBucket(
            name=f'filament_task_run:{self.type.func_address}',
            rate_limit=int(self.config.rate_limit * 100),
            capacity=int(self.config.rate_limit * 400),
        )
        await bucket.acquire(tokens=100)
        yield

    @asynccontextmanager
    async def _acquire_semaphore(self):
        if self.config.max_concurrent is None:
            yield
            return
        try:
            heartbeat_interval = self.config.heartbeat_interval or DEFAULT_HEARTBEAT_INTERVAL
            semaphore = RedisSemaphore(
                name=f'filament_task_run:{self.type.func_address}',
                max_leases=self.config.max_concurrent,
                ttl=self.config.timeout or 3600,  # must be set to avoid deadlocking
                heartbeat_interval=heartbeat_interval,
                heartbeat_ttl=heartbeat_interval * 4,
            )
            async with semaphore:
                yield
        except Exception as e:
            self._logger.error('Failed to acquire semaphore')
            self._logger.exception(e)
            raise

    @asynccontextmanager
    async def _transition_running_state(self):
        await transition_state(self.uuid, TaskState.RUNNING)
        yield
        await transition_state(self.uuid, TaskState.SUCCESS)

    @asynccontextmanager
    async def _transition_timeout_state(self):
        try:
            with anyio.fail_after(self.config.timeout):
                yield
        except TimeoutError:
            await transition_state(self.uuid, TaskState.TIMEOUT)
            raise

    @asynccontextmanager
    async def _transition_cancel_state(self):
        try:
            yield
        except anyio.get_cancelled_exc_class():
            await transition_state(self.uuid, TaskState.CANCELLED)
            raise

    @asynccontextmanager
    async def _transition_failure_state(self):
        try:
            yield
        except Exception as e:
            self._logger.exception(e)
            await transition_state(self.uuid, TaskState.FAILURE)
            raise

    def _retry(self, func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            retry_exc_types = tuple([exc_type._exc_type for exc_type in self.config.retry_exceptions])
            no_retry_exc_types = tuple([exc_type._exc_type for exc_type in self.config.no_retry_exceptions])
            for i in range(self.config.tries):
                try:
                    self._try_index = i
                    return await func(*args, **kwargs)
                except no_retry_exc_types:
                    raise
                except anyio.get_cancelled_exc_class():
                    # do not attempt to retry if cancelled
                    raise
                except retry_exc_types as e:
                    if i < self.config.tries - 1:
                        self._logger.exception(e)
                        await transition_state(self.uuid, TaskState.RETRYING)
                        if self.config.delay:
                            sleep_time = self.config.delay * self.config.backoff_base**i * random.uniform(1.0, 1.5)
                            await anyio.sleep(sleep_time)
                    else:
                        raise

        return wrapper

    def _cache_results(self, func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if not self.config.cache:
                return await func(*args, **kwargs)
            cache_key = self.config.cache_key._func
            key = cache_key(self.type._func, self._get_call_parameters())
            if await cache_has_key(key) and not self.config.refresh_cache:
                result = await cache_get(key)
                await anyio.sleep(random.uniform(0.1, 2.0))
                await transition_state(self.uuid, TaskState.CACHED)
                return result
            result = await func(*args, **kwargs)
            await cache_set(key, result, ttl=self.config.cache_ttl)
            return result

        return wrapper

    def _get_call_parameters(self) -> dict:
        args = self.task_args
        kwargs = self.task_kwargs
        signature = inspect.signature(self.type._func)
        filled_parameters = {k: v for k, v in kwargs.items()}
        for i, name in enumerate(signature.parameters.keys()):
            if i < len(args):
                filled_parameters[name] = args[i]
            elif name in kwargs:
                filled_parameters[name] = kwargs.get(name)
            else:
                parameter = signature.parameters[name]
                if parameter.default is not parameter.empty:
                    filled_parameters[name] = parameter.default
        return filled_parameters

    async def _call(self, task_group: TaskGroup) -> None:
        try:
            async with self._transition_failure_state():
                async with self._transition_cancel_state():

                    @self._retry
                    async def _inner():
                        async with self._acquire_semaphore():
                            async with self._acquire_token_bucket():
                                async with self._transition_timeout_state():

                                    @self._cache_results
                                    async def __inner():
                                        async with self._transition_running_state():
                                            with self._register_frame():
                                                if inspect.iscoroutinefunction(self.type._func):
                                                    return await self.type._func(*self.task_args, **self.task_kwargs)
                                                elif inspect.isasyncgenfunction(self.type._func):
                                                    item = None
                                                    async for item in self.type._func(
                                                        *self.task_args, **self.task_kwargs
                                                    ):
                                                        await self._result_send.send(item)
                                                    return item
                                                elif inspect.isfunction(self.type._func):
                                                    return self.type._func(*self.task_args, **self.task_kwargs)
                                                else:
                                                    raise TypeError(
                                                        f'Unsupported function type: {get_function_type(self.type._func)}'
                                                    )

                                    return await __inner()

                    self._result = await _inner()
        except Exception as e:
            self._exception = e
        except anyio.get_cancelled_exc_class() as e:
            self._exception = e
        finally:
            await self._result_send.aclose()
            self._done_event.set()
            await set_task_result(
                self.uuid,
                self._result,
                self._exception,
                is_redact=self.config.is_redact_output,
            )
            task_group.cancel_scope.cancel()

    async def call(self):
        await initialize_task_run_state(self)
        async with anyio.create_task_group() as task_group:
            if self.config.heartbeat:
                task_group.start_soon(self._start_heartbeat)
            if self.config.monitor:
                task_group.start_soon(self._start_cancel_monitor, task_group)
            task_group.start_soon(self._call, task_group)
        await self._done_event.wait()
        return await self.result()

    def __await__(self):
        if not (inspect.isfunction(self.type._func) or inspect.iscoroutinefunction(self.type._func)):
            raise TypeError(f'Unsupported function type: {get_function_type(self.type._func)}')
        return self.start().__await__()

    async def __aiter__(self):
        if not inspect.isasyncgenfunction(self.type._func):
            raise TypeError(f'Unsupported function type: {get_function_type(self.type._func)}')
        self.start()
        chunk = None
        while True:
            try:
                chunk = await self._result_receive.receive()
                yield chunk
            except anyio.EndOfStream:
                break
        await self._done_event.wait()
        result = await self.result()
        if result != chunk:
            yield result

    async def result(self):
        if not self._done_event.is_set():
            await self.start()
        if self._exception:
            if self.config.propagate:
                raise self._exception
            return self._exception
        return self._result
