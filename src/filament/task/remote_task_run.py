import anyio
from anyio.abc import TaskGroup
from beartype import beartype

from filament.task.queue.task_queue import (
    enqueue_task_run,
    listen_for_task_result,
)


from filament.task.task_run import FilamentTaskRun
from filament.task.state.task_run_state import initialize_task_run_state
from filament.task.task_result import FilamentTaskResult


class FilamentRemoteTaskRun(FilamentTaskRun):
    async def call(self):
        await initialize_task_run_state(self)
        await enqueue_task_run(self)
        async with anyio.create_task_group() as task_group:
            if self.config.monitor:
                task_group.start_soon(self._start_cancel_monitor, task_group)
            task_group.start_soon(self._listen_for_task_result, task_group)
        await self._done_event.wait()
        return await self.result()

    @beartype
    async def _listen_for_task_result(self, task_group: TaskGroup) -> None:
        result, exception = None, None
        is_final = False
        task_result_json = None
        try:
            async for task_result_json, is_final in listen_for_task_result(self.uuid):
                # self._logger.debug(f'remote received {task_result_json}, is_final: {is_final}')
                task_result = FilamentTaskResult.model_validate_json(task_result_json)
                result, exception = task_result._result, task_result._exception
                if not is_final:
                    assert exception is None, f'Exception only allowed on final chunk: {task_result._exception}'
                    await self._result_send.send(result)
            assert is_final, f'Expected final result, got {task_result_json}'
            self._result, self._exception = result, exception
        except Exception as e:
            self._exception = e
        except anyio.get_cancelled_exc_class() as e:
            self._exception = e
        finally:
            await self._result_send.aclose()
            self._done_event.set()
            task_group.cancel_scope.cancel()
