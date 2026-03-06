import asyncio
import functools
import inspect
import json
import logging
import math
import random
import traceback
import types
from contextlib import asynccontextmanager, contextmanager
from typing import Optional, Union
from uuid import uuid4

import anyio
import sentry_sdk
from anyio.abc import TaskGroup
from beartype import beartype
from pydantic import BaseModel, Field, PrivateAttr
from sentry_sdk.integrations.logging import ignore_logger

from filament.cache_keys import hash_cache_key
from filament.cache_utils import (
    cache_get,
    cache_has_key,
    cache_set,
)
from filament.db_models import TaskState
from filament.db_session import async_session_scope
from filament.func_registry import lookup_func_entry, register_func
from filament.logic.module_type_registry import lookup_module_type, register_module_type
from filament.logic.task_type_registry import register as register_task_type
from filament.redis_handler import JSONFormatter, RedisHandler
from filament.redis_semaphore import RedisSemaphore
from filament.redis_token_bucket import RedisTokenBucket
from filament.task_queue import (
    dequeue_task_run,
    enqueue_task_run,
    listen_for_task_result,
    publish_task_result,
    setup_queue,
)
from filament.task_state import (
    create_task_run_state,
    get_parent_task_run_uuid,
    get_task_run_state,
    is_canceled,
    set_heartbeat,
    set_parent_task_uuid,
    set_task_result,
    transition_state,
)
from filament.utils import get_function_type, json_encode_safe
from filament.utils_call_stack import peek_task_run, pop_task_run, push_task_run

DEFAULT_HEARTBEAT_INTERVAL = 60
DEFAULT_MONITOR_INTERVAL = 10


class FilamentBaseModel(BaseModel):
    def __hash__(self):
        return hash(self.model_dump_json())


class FilamentExceptionType(FilamentBaseModel):
    exc_type_address: str
    _exc_type: type = PrivateAttr()

    def __init__(self, exc_type=None, **kwargs):
        if exc_type is not None:
            kwargs['exc_type_address'] = register_module_type(exc_type)
        super().__init__(**kwargs)

    def model_post_init(self, __context):
        self._exc_type = lookup_module_type(self.exc_type_address)


class FilamentCacheKey(FilamentBaseModel):
    func_address: str
    _func: callable = PrivateAttr()

    def __init__(self, func=None, **kwargs):
        if func is not None:
            kwargs['func_address'] = register_module_type(func)
        super().__init__(**kwargs)

    def model_post_init(self, __context):
        self._func = lookup_module_type(self.func_address)


class FilamentTaskConfig(FilamentBaseModel):
    timeout: float | None = Field(default=None)
    start_immediately: bool = Field(default=False)
    propagate: bool = Field(default=True)
    tries: int = Field(default=1)
    delay: float = Field(default=0)
    backoff_base: float = Field(default=2)
    retry_exceptions: list['FilamentExceptionType'] = Field(default=[FilamentExceptionType(Exception)])
    cache: bool = Field(default=False)
    cache_key: 'FilamentCacheKey' = Field(default=FilamentCacheKey(hash_cache_key))
    cache_ttl: int | None = Field(default=None)
    refresh_cache: bool = Field(default=False)
    heartbeat: bool = Field(default=True)
    heartbeat_interval: float | None = Field(default=DEFAULT_HEARTBEAT_INTERVAL)
    monitor: bool = Field(default=True)
    monitor_interval: float | None = Field(default=DEFAULT_MONITOR_INTERVAL)
    max_concurrent: int | None = Field(default=None)
    rate_limit: float | None = Field(default=None)
    disable_sentry: bool = Field(default=False)
    is_redact_input: bool = Field(default=False)
    is_redact_output: bool = Field(default=False)

    def __init__(self, **kwargs):
        if 'retry_exceptions' in kwargs:
            kwargs['retry_exceptions'] = [
                FilamentExceptionType(exc_type)
                if isinstance(exc_type, type) and issubclass(exc_type, Exception)
                else exc_type
                for exc_type in kwargs['retry_exceptions']
            ]
        if 'cache_key' in kwargs:
            kwargs['cache_key'] = (
                FilamentCacheKey(kwargs['cache_key']) if callable(kwargs['cache_key']) else kwargs['cache_key']
            )
        super().__init__(**kwargs)


class FilamentTaskRun(FilamentBaseModel):
    type: 'FilamentTaskType'
    config: 'FilamentTaskConfig' = Field(default_factory=lambda: FilamentTaskConfig())
    uuid: str
    task_args: tuple = Field(default=())
    task_kwargs: dict = Field(default={})
    name: str

    def __init__(
        self,
        type: 'FilamentTaskType',
        task_args,
        task_kwargs,
        name=None,
        uuid=None,
        config: Optional[Union['FilamentTaskConfig', dict]] = None,
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
        ignore_logger(logger_name)  # use sentry_sdk.capture_exception instead
        # a little scary to run the task on init, in case there's a concurrent worker
        if self.config.start_immediately:
            self.start()

    def start(self):
        if self._task:
            return self._task
        self._task = asyncio.create_task(self.call())
        return self._task

    @beartype
    async def _start_heartbeat(self) -> None:
        while not self._done_event.is_set():
            await set_heartbeat(self.uuid)
            await anyio.sleep(self.config.heartbeat_interval or DEFAULT_HEARTBEAT_INTERVAL)

    @beartype
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

    @asynccontextmanager
    async def _sentry_context(self):
        if self.config.disable_sentry:
            yield
        else:
            has_parent_frame = (await get_parent_task_run_uuid(self.uuid)) is not None
            start_sentry_context = sentry_sdk.start_span if has_parent_frame else sentry_sdk.start_transaction
            with sentry_sdk.new_scope() as scope:
                scope.set_tag('filament.task_run.uuid', self.uuid)
                scope.set_tag('filament.task_run.type.func_address', self.type.func_address)
                with start_sentry_context(op='filament.task_run', name=self.type.name):
                    try:
                        yield
                    except Exception as e:
                        if not (hasattr(e, 'is_sentry_reported') and e.is_sentry_reported):
                            scope.capture_exception(e)
                            e.is_sentry_reported = True
                        raise

    def _retry(self, func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            retry_exc_types = tuple([exc_type._exc_type for exc_type in self.config.retry_exceptions])
            for i in range(self.config.tries):
                try:
                    self._try_index = i
                    return await func(*args, **kwargs)
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

    @beartype
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

    @beartype
    async def _call(self, task_group: TaskGroup) -> None:
        try:
            async with self._sentry_context():
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
                                                        return await self.type._func(
                                                            *self.task_args, **self.task_kwargs
                                                        )
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


class FilamentRemoteTaskRun(FilamentTaskRun):
    async def call(self):
        await initialize_task_run_state(self)
        await enqueue_task_run(self)
        result, exception = None, None
        try:
            async for task_result_json, is_final in listen_for_task_result(self.uuid):
                # self._logger.debug(f'remote received {task_result_json}, is_final: {is_final}')
                task_result = FilamentTaskResult.model_validate_json(task_result_json)
                result, exception = task_result._result, task_result._exception
                if not is_final:
                    assert exception is None, f'Exception only allowed on final chunk: {task_result._exception}'
                    await self._result_send.send(result)
        finally:
            await self._result_send.aclose()
        assert is_final, f'Expected final result, got {task_result_json}'
        self._result, self._exception = result, exception
        self._done_event.set()
        return await self.result()


class FilamentRemoteException(Exception):
    def __init__(self, exc_type, message, traceback=None):
        self.exc_type = exc_type
        self.message = message
        self.traceback = traceback

    def __str__(self):
        result = f'{self.exc_type.__name__}: {self.message}'
        if self.traceback:
            result += f'\n{self.traceback}'
        return result

    def __repr__(self):
        return f'{self.exc_type.__name__}: {self.message}'


class FilamentTaskResult(FilamentBaseModel):
    type: 'FilamentTaskType'
    task_uuid: str
    result_json: str | None = Field(default=None)
    exception_json: str | None = Field(default=None)
    _result: any = PrivateAttr(default=None)
    _exception: Exception | None = PrivateAttr(default=None)

    def __init__(self, result=None, exception=None, **kwargs):
        if result is not None:
            kwargs['result_json'] = json.dumps(json_encode_safe(result))
        if exception is not None:
            kwargs['exception_json'] = json.dumps(
                {
                    'type_address': register_module_type(type(exception)),
                    'message': str(exception),
                    # "args": base64.b64encode(pickle.dumps(exception.args)).decode(),
                    'traceback': traceback.format_exc(),
                }
            )
        super().__init__(**kwargs)

    def model_post_init(self, __context):
        if self.result_json is not None:
            self._result = json.loads(self.result_json)
        if self.exception_json is not None:
            exception_dict = json.loads(self.exception_json)
            exc_type = lookup_module_type(exception_dict['type_address'])
            message = exception_dict['message']
            traceback = exception_dict['traceback']
            # self._exception = exc_type(message)
            self._exception = FilamentRemoteException(exc_type=exc_type, message=message, traceback=traceback)
            # args = pickle.loads(base64.b64decode(exception_dict["args"]))
            # self._exception = exc_type(*args)


class FilamentTaskType(FilamentBaseModel):
    func_address: str
    name: str
    _func: callable = PrivateAttr()
    config: FilamentTaskConfig = Field(default_factory=lambda: FilamentTaskConfig())

    def __init__(
        self,
        _func=None,
        func_address=None,
        name=None,
        **config_kwargs,
    ):
        if _func is not None:
            func_address = register_func(_func).func_address
        else:
            assert func_address is not None, 'func_address must be provided if func is not'
            _func = lookup_func_entry(func_address).func
        assert inspect.iscoroutinefunction(_func) or inspect.isasyncgenfunction(_func), f'Unsupported function: {_func}'
        if name is None:
            name = func_address
        config = FilamentTaskConfig(**config_kwargs)
        super().__init__(
            func_address=func_address,
            name=name,
            config=config,
        )
        self._func = _func
        self._logger = logging.getLogger(func_address)
        ignore_logger(func_address)  # use sentry_sdk.capture_exception instead

    def model_post_init(self, __context):
        func_entry = lookup_func_entry(self.func_address)
        self._func = func_entry.func

    async def _dequeue_task_run(self, worker_id: str, shutdown_event: anyio.Event) -> tuple[str | None, str | None]:
        message_id, filament_task_run_json = None, None
        async with anyio.create_task_group() as task_group:

            async def _wait_for_dequeue_task_run(cancel_scope: anyio.CancelScope):
                nonlocal message_id, filament_task_run_json
                message_id, filament_task_run_json = await dequeue_task_run(self, worker_id)
                cancel_scope.cancel()

            async def _wait_for_shutdown(cancel_scope: anyio.CancelScope):
                await shutdown_event.wait()
                cancel_scope.cancel()

            task_group.start_soon(_wait_for_dequeue_task_run, task_group.cancel_scope)
            task_group.start_soon(_wait_for_shutdown, task_group.cancel_scope)

        return message_id, filament_task_run_json

    async def serve(self, shutdown_event: anyio.Event):
        worker_id = str(uuid4())
        await setup_queue(self)
        while not shutdown_event.is_set():
            message_id, filament_task_run_json = await self._dequeue_task_run(worker_id, shutdown_event)
            if message_id is None or filament_task_run_json is None:
                continue
            try:
                filament_task_run = FilamentTaskRun.model_validate_json(filament_task_run_json)
                filament_task_run.config.propagate = True  # always propagate so we can catch and serialize
            except Exception as e:
                self._logger.exception(e)
                continue
            result, exception = None, None
            if inspect.isasyncgenfunction(self._func):
                try:
                    async for result in filament_task_run:
                        task_result = FilamentTaskResult(
                            type=self,
                            task_uuid=filament_task_run.uuid,
                            result=result,
                            exception=exception,
                        )
                        await publish_task_result(task_result, is_final=False)
                except (Exception, anyio.get_cancelled_exc_class()) as e:
                    exception = e
                    self._logger.exception(e)
            else:
                try:
                    result = await filament_task_run
                except (Exception, anyio.get_cancelled_exc_class()) as e:
                    exception = e
                    self._logger.exception(e)
            task_result = FilamentTaskResult(
                type=self,
                task_uuid=filament_task_run.uuid,
                result=result,
                exception=exception,
            )
            await publish_task_result(task_result, is_final=True, message_id=message_id)

    @beartype
    async def request(self, *task_args, **task_kwargs) -> FilamentRemoteTaskRun:
        return await self._request(task_args, task_kwargs)

    @beartype
    async def _request(self, task_args, task_kwargs) -> FilamentRemoteTaskRun:
        task_run = FilamentRemoteTaskRun(
            type=self,
            task_args=task_args,
            task_kwargs=task_kwargs,
            config=self.config,
        )
        await initialize_task_run_state(task_run)
        return task_run

    @beartype
    def __call__(self, *task_args, **task_kwargs) -> FilamentTaskRun:
        return FilamentTaskRun(
            type=self,
            task_args=task_args,
            task_kwargs=task_kwargs,
            config=self.config,
        )

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return types.MethodType(self, instance)


@beartype
async def initialize_task_run_state(task_run: FilamentTaskRun) -> None:
    # lock so that we're not interrupted if initialize_task_run_state is called concurrently
    semaphore = RedisSemaphore(
        name=f'filament_task_run:initialize_task_run_state:{task_run.uuid}', max_leases=1, ttl=60
    )
    async with semaphore:
        async with async_session_scope() as session:
            task_run_state = await get_task_run_state(session, task_run.uuid)
            if task_run_state is None:
                await create_task_run_state(
                    session=session,
                    task_uuid=task_run.uuid,
                    func_address=task_run.type.func_address,
                    name=task_run.name,
                    parameters=task_run._get_call_parameters(),
                    is_redact=task_run.config.is_redact_input,
                )
                parent_task_run = peek_task_run()
                if parent_task_run is not None:
                    await set_parent_task_uuid(session, task_run.uuid, parent_task_run.uuid)


def get_logger():
    task_run = peek_task_run()
    if task_run is not None:
        return logging.getLogger(f'{task_run.type.func_address}:{task_run.uuid}')
    # no task found, return a default logger for the caller
    parent_frame = inspect.currentframe().f_back
    parent_frame_module_name = parent_frame.f_globals.get('__name__', 'unknown')
    parent_frame_func_name = parent_frame.f_code.co_name
    return logging.getLogger(f'{parent_frame_module_name}:{parent_frame_func_name}')


def task(*wrapper_args, **wrapper_kwargs):
    func = None
    if len(wrapper_args) == 1 and callable(wrapper_args[0]):
        func = wrapper_args[0]

    def get_wrapper(
        func,
        **wrapper_kwargs,
    ):
        task_type = FilamentTaskType(func, **wrapper_kwargs)
        register_task_type(task_type)
        return task_type

    get_wrapper = functools.partial(get_wrapper, **wrapper_kwargs)
    if func is not None:
        return get_wrapper(func)
    return get_wrapper
