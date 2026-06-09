import inspect
from uuid import uuid4

import anyio

from filament.queue.task_queue import (
    dequeue_task_run,
    publish_task_result,
    setup_queue,
)
from filament.state.task_run_state import initialize_task_run_state

from filament.task.types.task_type import FilamentTaskType
from filament.task.types.task_run import FilamentTaskRun
from filament.queue.types.remote_task_result import FilamentRemoteTaskResult
from filament.queue.types.remote_task_run import FilamentRemoteTaskRun


class FilamentRemoteTaskType(FilamentTaskType):
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
                        task_result = FilamentRemoteTaskResult(
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
            task_result = FilamentRemoteTaskResult(
                type=self,
                task_uuid=filament_task_run.uuid,
                result=result,
                exception=exception,
            )
            await publish_task_result(task_result, is_final=True, message_id=message_id)

    async def request(self, *task_args, **task_kwargs) -> FilamentRemoteTaskRun:
        return await self._request(task_args, task_kwargs)

    async def _request(self, task_args, task_kwargs) -> FilamentRemoteTaskRun:
        task_run = FilamentRemoteTaskRun(
            type=self,
            task_args=task_args,
            task_kwargs=task_kwargs,
            config=self.config,
        )
        await initialize_task_run_state(task_run)
        return task_run
