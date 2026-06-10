import json
from typing import TYPE_CHECKING

from beartype import beartype
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament.db.models import TaskRun, TaskRunStateTransition, TaskType, get_utc_now
from filament.logic.utils import json_encode_safe, redact_strings
from filament.state.common import with_session
from filament.task.constants import TaskState

if TYPE_CHECKING:
    from filament.task.types.task_run import FilamentTaskRun
else:
    FilamentTaskRun = 'filament.task.types.task_run.FilamentTaskRun'


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


@with_session
@beartype
async def set_heartbeat(session: AsyncSession, task_run: FilamentTaskRun) -> None:
    statement = select(TaskRun).where(TaskRun.task_uuid == task_run.uuid)
    task_run_row = (await session.execute(statement)).scalars().one()
    task_run_row.heartbeat = get_utc_now()


@with_session
@beartype
async def create_task_run_state(session: AsyncSession, task_run: FilamentTaskRun) -> TaskRun:
    statement = select(TaskType).where(TaskType.func_address == task_run.type.func_address)
    task_type = (await session.execute(statement)).scalars().one_or_none()
    if task_type is None:
        raise ValueError(f'No task type found for func_address {task_run.type.func_address}')
    task_run_row = TaskRun(name=task_run.name, task_uuid=task_run.uuid, task_type_id=task_type.id)
    parameters = task_run._get_call_parameters()
    if parameters is not None:
        encodable_parameters = json_encode_safe(parameters)
        if task_run.config.is_redact_input:
            encodable_parameters = redact_strings(encodable_parameters)
        task_run_row.parameters_json = json.dumps(encodable_parameters, separators=(',', ':'), default=str)
    session.add(task_run_row)
    return task_run_row


@with_session
@beartype
async def transition_state(session: AsyncSession, task_run: FilamentTaskRun, new_state: TaskState) -> None:
    statement = select(TaskRun).where(TaskRun.task_uuid == task_run.uuid)
    task_run_row = (await session.execute(statement)).scalars().one()
    old_state = task_run_row.state
    if old_state == new_state:
        return
    if new_state == TaskState.RUNNING:
        task_run_row.run_count += 1
    task_run_row.state = new_state
    task_run_row.state_since = get_utc_now()
    transition = TaskRunStateTransition(
        task_uuid=task_run.uuid, from_state=old_state, to_state=new_state, state_since=task_run_row.state_since
    )
    session.add(transition)


@with_session
@beartype
async def set_task_result(session: AsyncSession, task_run: FilamentTaskRun) -> None:
    statement = select(TaskRun).where(TaskRun.task_uuid == task_run.uuid)
    task_run_row = (await session.execute(statement)).scalars().one()
    encodable_result = json_encode_safe(task_run._result or task_run._exception)
    if task_run.config.is_redact_output:
        encodable_result = redact_strings(encodable_result)
    task_run_row.result_json = json.dumps(encodable_result, separators=(',', ':'), default=str)


@with_session
@beartype
async def is_canceled(session: AsyncSession, task_uuid: str) -> bool:
    statement = select(TaskRun).where(TaskRun.task_uuid == task_uuid)
    task_run_row = (await session.execute(statement)).scalars().one()
    return task_run_row.state == TaskState.CANCELLED
