import asyncio
import base64
import functools
import inspect
import json
import logging
import math
import pickle
import random
import traceback
from contextlib import asynccontextmanager, contextmanager
from uuid import uuid4

import anyio
import sentry_sdk
from pydantic import BaseModel, Field, PrivateAttr
from sentry_sdk.integrations.logging import ignore_logger

from filament.cache_keys import hash_cache_key
from filament.cache_utils import (
    cache_get,
    cache_has_key,
    cache_set,
)
from filament.func_registry import (
    lookup_func,
    register_func,
)
from filament.redis_handler import JSONFormatter, RedisHandler
from filament.redis_semaphore import RedisSemaphore
from filament.redis_token_bucket import RedisTokenBucket
from filament.task_queue import (
    dequeue_task_run,
    enqueue_task_run,
    get_task_result,
    listen_for_task_result,
    publish_task_result,
    setup_queue,
)
from filament.task_state import (
    TaskState,
    create_task_run_state,
    create_task_type_state,
    get_parent_task_uuid,
    is_canceled,
    set_heartbeat,
    set_parent_task_uuid,
    set_task_result,
    transition_state,
)
from filament.task_state import (
    get_task_run as get_task_run_state,
)
from filament.utils import get_arg_name, get_function_type, json_encode_safe
from filament.utils_dependency import (
    get_frame_task_run,
    register_frame,
    unregister_frame,
)


class FilamentBaseModel(BaseModel):
    def __hash__(self):
        return hash(self.model_dump_json())


class FilamentExceptionType(FilamentBaseModel):
    exc_type_address: str
    _exc_type: type = PrivateAttr()

    def __init__(self, exc_type=None, **kwargs):
        if exc_type is not None:
            kwargs['exc_type_address'] = register_func(exc_type)
        super().__init__(**kwargs)

    def model_post_init(self, __context):
        self._exc_type = lookup_func(self.exc_type_address)


class FilamentCacheKey(FilamentBaseModel):
    func_address: str
    _func: callable = PrivateAttr()

    def __init__(self, func=None, **kwargs):
        if func is not None:
            kwargs['func_address'] = register_func(func)
        super().__init__(**kwargs)

    def model_post_init(self, __context):
        self._func = lookup_func(self.func_address)


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
    heartbeat_interval: float | None = Field(default=1)
    monitor: bool = Field(default=True)
    monitor_interval: float | None = Field(default=1)
    max_concurrent: int | None = Field(default=None)
    rate_limit: float | None = Field(default=None)
    disable_sentry: bool = Field(default=False)

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
        config: 'FilamentTaskConfig' = None,
    ):
        for config_name in FilamentTaskConfig.model_fields.keys():
            if config_name in task_kwargs:
                config_value = task_kwargs[config_name]
                signature = inspect.signature(type._func)
                if config_name not in signature.parameters.keys():
                    task_kwargs.pop(config_name)
                setattr(config, config_name, config_value)

        if name is None:
            name = f'{type.name}({get_arg_name(*task_args, **task_kwargs)})'

        if uuid is None:
            uuid = str(uuid4())

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

    async def _start_heartbeat(self):
        while not self._done_event.is_set():
            set_heartbeat(self.uuid)
            await anyio.sleep(self.config.heartbeat_interval or 1)

    async def _start_cancel_monitor(self, task_group):
        while not self._done_event.is_set():
            if is_canceled(self.uuid):
                task_group.cancel_scope.cancel()
            await anyio.sleep(self.config.monitor_interval or 1)

    async def cancel(self):
        transition_state(self.uuid, TaskState.CANCELLED)

    @contextmanager
    def _register_frame(self):
        stack = inspect.stack()
        frame = stack[2].frame  # 0 is self, 1 is contextmanager, 2 is _call
        register_frame(self, frame)
        try:
            yield
        finally:
            unregister_frame(frame)

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
            heartbeat_interval = self.config.heartbeat_interval or 1
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

    @contextmanager
    def _transition_running_state(self):
        transition_state(self.uuid, TaskState.RUNNING)
        yield
        transition_state(self.uuid, TaskState.SUCCESS)

    @contextmanager
    def _transition_timeout_state(self):
        try:
            with anyio.fail_after(self.config.timeout):
                yield
        except TimeoutError:
            transition_state(self.uuid, TaskState.TIMEOUT)
            raise

    @contextmanager
    def _transition_cancel_state(self):
        try:
            yield
        except anyio.get_cancelled_exc_class():
            transition_state(self.uuid, TaskState.CANCELLED)
            raise

    @contextmanager
    def _transition_failure_state(self):
        try:
            yield
        except Exception as e:
            self._logger.exception(e)
            transition_state(self.uuid, TaskState.FAILURE)
            raise

    @contextmanager
    def _sentry_context(self):
        if self.config.disable_sentry:
            yield
        else:
            has_parent_frame = get_parent_task_uuid(self.uuid) is not None
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
                        transition_state(self.uuid, TaskState.RETRYING)
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
                transition_state(self.uuid, TaskState.CACHED)
                return result
            result = await func(*args, **kwargs)
            await cache_set(key, result, ttl=self.config.cache_ttl)
            return result

        return wrapper

    def _get_call_parameters(self):
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

    async def _call(self, task_group):
        try:
            with self._sentry_context():
                with self._transition_failure_state():
                    with self._transition_cancel_state():

                        @self._retry
                        async def _inner():
                            async with self._acquire_semaphore():
                                async with self._acquire_token_bucket():
                                    with self._transition_timeout_state():

                                        @self._cache_results
                                        async def __inner():
                                            with self._transition_running_state():
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
        finally:
            await self._result_send.aclose()
            self._done_event.set()
            task_group.cancel_scope.cancel()
            set_task_result(self.uuid, self._result, self._exception)

    async def call(self):
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
                    'type_address': register_func(type(exception)),
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
            exc_type = lookup_func(exception_dict['type_address'])
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
            func_address = register_func(_func)
        else:
            assert func_address is not None, 'func_address must be provided if func is not'
            _func = lookup_func(func_address)
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
        self._func = lookup_func(self.func_address)
        create_task_type_state(self.func_address, name=self.name)

    async def serve(self):
        worker_id = str(uuid4())
        await setup_queue(self)
        while True:
            message_id, filament_task_run_json = await dequeue_task_run(self, worker_id)
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
                except Exception as e:
                    exception = e
                    self._logger.exception(e)
            else:
                try:
                    result = await filament_task_run
                except Exception as e:
                    exception = e
                    self._logger.exception(e)
            task_result = FilamentTaskResult(
                type=self,
                task_uuid=filament_task_run.uuid,
                result=result,
                exception=exception,
            )
            await publish_task_result(task_result, is_final=True, message_id=message_id)

    def request(self, *task_args, **task_kwargs):
        task_run = FilamentRemoteTaskRun(
            type=self,
            task_args=task_args,
            task_kwargs=task_kwargs,
            config=self.config,
        )
        create_task_run_state(
            task_uuid=task_run.uuid,
            func_address=self.func_address,
            name=task_run.name,
            parameters=task_run._get_call_parameters(),
        )
        detect_dependency(task_run.uuid)
        if inspect.iscoroutinefunction(self._func) or inspect.isasyncgenfunction(self._func):
            return task_run
        elif inspect.isfunction(self._func):
            with anyio.from_thread.start_blocking_portal() as portal:
                return portal.call(task_run.call)
        else:
            raise TypeError(f'Unsupported function type: {get_function_type(self._func)}')

    def __call__(self, *task_args, **task_kwargs):
        task_run = FilamentTaskRun(
            type=self,
            task_args=task_args,
            task_kwargs=task_kwargs,
            config=self.config,
        )
        create_task_run_state(
            task_uuid=task_run.uuid,
            func_address=self.func_address,
            name=task_run.name,
            parameters=task_run._get_call_parameters(),
        )
        detect_dependency(task_run.uuid)
        if inspect.iscoroutinefunction(self._func) or inspect.isasyncgenfunction(self._func):
            return task_run
        elif inspect.isfunction(self._func):
            with anyio.from_thread.start_blocking_portal() as portal:
                return portal.call(task_run.call)
        else:
            raise TypeError(f'Unsupported function type: {get_function_type(self._func)}')


def get_logger():
    stack = inspect.stack()
    for frame_info in stack:
        frame = frame_info.frame
        task_run = get_frame_task_run(frame)
        if task_run:
            return logging.getLogger(f'{task_run.type.func_address}:{task_run.uuid}')
    # no task found, return a default logger for the caller
    parent_frame = stack[1]
    parent_frame_module_name = inspect.getmodule(parent_frame.frame).__name__
    parent_frame_func_name = parent_frame.function
    return logging.getLogger(f'{parent_frame_module_name}:{parent_frame_func_name}')


def get_task_run():
    stack = inspect.stack()
    for frame_info in stack:
        frame = frame_info.frame
        task_run = get_frame_task_run(frame)
        if task_run:
            return task_run
    raise RuntimeError('No task found in stack')


def detect_dependency(task_uuid):
    stack = inspect.stack()
    for frame_info in stack:
        parent_frame = frame_info.frame
        # print(f"Considering parent frame {parent_frame}")
        parent_task_run = get_frame_task_run(parent_frame)
        if parent_task_run:
            # register_dependency(self.uuid, parent_task_uuid)
            set_parent_task_uuid(task_uuid, parent_task_run.uuid)
            break


TASK_TYPE_REGISTRY = {}


def task(*wrapper_args, **wrapper_kwargs):
    func = None
    if len(wrapper_args) == 1 and callable(wrapper_args[0]):
        func = wrapper_args[0]

    def get_wrapper(
        func,
        **wrapper_kwargs,
    ):
        task_type = FilamentTaskType(func, **wrapper_kwargs)
        TASK_TYPE_REGISTRY[task_type.func_address] = task_type
        signature = inspect.signature(func)
        arg_names = list(signature.parameters.keys())
        if len(arg_names) > 0 and arg_names[0] == 'self':
            # we must return a bound method
            if inspect.iscoroutinefunction(func):

                @functools.wraps(func)
                async def wrapper(*args, **kwargs):
                    return await task_type(*args, **kwargs)
            elif inspect.isasyncgenfunction(func):

                @functools.wraps(func)
                async def wrapper(*args, **kwargs):
                    async for item in task_type(*args, **kwargs):
                        yield item
            elif inspect.isfunction(func):

                @functools.wraps(func)
                def wrapper(*args, **kwargs):
                    return task_type(*args, **kwargs)
            else:
                raise TypeError(f'Unsupported function type: {get_function_type(func)}')
            return wrapper
        else:
            return task_type

    get_wrapper = functools.partial(get_wrapper, **wrapper_kwargs)
    if func is not None:
        return get_wrapper(func)
    return get_wrapper


def lookup(task_address):
    assert task_address in TASK_TYPE_REGISTRY, f'Task {task_address} not found'
    return TASK_TYPE_REGISTRY.get(task_address)


def print_task_registry():
    print(TASK_TYPE_REGISTRY.keys())


async def wait_for_remote_task_run(task_uuid, propagate=True, timeout=None):
    with anyio.fail_after(timeout):
        # TODO: propagate exceptions
        await wait_for_task(task_uuid)


async def get_remote_task_run_results(task_uuid, propagate=False, timeout=None):
    with anyio.fail_after(timeout):
        async for result in generate_remote_task_run_results(task_uuid, propagate=propagate):
            pass
        return result


async def generate_remote_task_run_results(task_uuid, propagate=False, check_state_interval=1):
    task_result_json, is_final = None, False
    listen_generator = listen_for_task_result(task_uuid)

    while not is_final:
        async with anyio.create_task_group() as task_group:

            async def _wait_for_state():
                nonlocal task_result_json, is_final
                await wait_for_task(task_uuid, check_state_interval=check_state_interval)
                task_result_json = await get_task_result(task_uuid)
                is_final = True
                task_group.cancel_scope.cancel()

            async def _wait_for_result():
                nonlocal task_result_json, is_final
                task_result_json, is_final = await anext(listen_generator)
                task_group.cancel_scope.cancel()

            task_group.start_soon(_wait_for_state)
            task_group.start_soon(_wait_for_result)

        # TODO: this currently fails if the task is not submitted
        assert task_result_json is not None, 'Task result is None'
        task_result = FilamentTaskResult.model_validate_json(task_result_json)
        if task_result._exception:
            if propagate:
                raise task_result._exception
            yield task_result._exception
        else:
            yield task_result._result


async def wait_for_task(task_uuid, check_state_interval=1):
    while True:
        task_run = get_task_run_state(task_uuid)
        if task_run['state'] in TaskState.TERMINAL:
            break
        await anyio.sleep(check_state_interval)
