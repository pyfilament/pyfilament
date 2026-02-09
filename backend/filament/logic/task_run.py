from beartype import beartype
from sqlalchemy.ext.asyncio import AsyncSession

from filament.db_models import TaskRun, TaskState
from filament.task_state import transition_state


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
