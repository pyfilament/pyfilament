import inspect
import logging
import types
from uuid import uuid4

import anyio
from beartype import beartype
from pydantic import Field, PrivateAttr

from filament.logic.func_registry import lookup_func_entry, register_func
from filament.task.queue.task_queue import (
    dequeue_task_run,
    publish_task_result,
    setup_queue,
)
from filament.task.task_run_state import initialize_task_run_state

from filament.task.base import FilamentBaseModel
from filament.task.task_config import FilamentTaskConfig
from filament.task.task_run import FilamentTaskRun
from filament.task.task_result import FilamentTaskResult
from filament.task.remote_task_run import FilamentRemoteTaskRun


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
                filament_task_run.worker_id = worker_id
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
