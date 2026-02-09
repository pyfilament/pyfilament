from filament.db_models import TaskRun, TaskState
from filament.task_state import transition_state


async def cancel_task_run(session, task_run: TaskRun):
    if task_run.state in TaskState.TERMINAL:
        return task_run
    await transition_state(session, task_run.task_uuid, TaskState.CANCELLED)
    for child_task_run in await task_run.awaitable_attrs.child_tasks:
        await cancel_task_run(session, child_task_run)


async def delete_task_run(session, task_run: TaskRun):
    for child_task_run in await task_run.awaitable_attrs.child_tasks:
        await delete_task_run(session, child_task_run)
    for task_run_state_transition in await task_run.awaitable_attrs.state_transitions:
        session.delete(task_run_state_transition)
    session.delete(task_run)
    session.flush()
