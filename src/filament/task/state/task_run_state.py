from typing import TYPE_CHECKING
from beartype import beartype
from sqlalchemy.ext.asyncio import AsyncSession

from filament.db.models import TaskRun
from filament.task.constants import TaskState
from filament.task.state.task_state import transition_state
from filament.redis.semaphore import RedisSemaphore


from filament.db.session import async_session_scope
from filament.task.state.task_state import (
    create_task_run_state,
    get_task_run_state,
    set_parent_task_uuid,
)
from filament.logic.call_stack import peek_task_run

if TYPE_CHECKING:
    from filament.task.types.task_run import FilamentTaskRun
else:
    FilamentTaskRun = 'filament.task.types.task_run.FilamentTaskRun'


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


@beartype
async def cancel_task_run(session: AsyncSession, task_run: TaskRun):
    if task_run.state in TaskState.TERMINAL:
        return task_run
    await transition_state(session, task_run.task_uuid, TaskState.CANCELLED)
    for child_task_run in await task_run.awaitable_attrs.child_tasks:
        await cancel_task_run(session, child_task_run)


@beartype
async def delete_task_run(session: AsyncSession, task_run: TaskRun):
    for child_task_run in await task_run.awaitable_attrs.child_tasks:
        await delete_task_run(session, child_task_run)
    for task_run_state_transition in await task_run.awaitable_attrs.state_transitions:
        await session.delete(task_run_state_transition)
    await session.delete(task_run)
    await session.flush()
