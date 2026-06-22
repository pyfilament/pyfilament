from typing import AsyncGenerator

import anyio
from beartype import beartype
from sqlalchemy import select

from filament.constants import DEFAULT_MONITOR_INTERVAL
from filament.db.models import TaskRun, TaskType
from filament.db.session import async_session_scope
from filament.logic.call_stack import peek_task_run
from filament.logic.events import EventManager
from filament.redis.semaphore import RedisSemaphore
from filament.state.task_run_state import (
    create_task_run_state,
    is_canceled,
    set_heartbeat,
    set_task_result,
    transition_state,
)
from filament.state.task_type_state import upsert_task_type_state
from filament.types.task_run import FilamentTaskRun


@beartype
def register_task_events(events: EventManager) -> None:
    events.on('task_run.request')(initialize_task_run_state)
    events.on('task_run.before_call')(initialize_task_run_state)
    events.on('task_run.created_task_group')(monitor_task_cancellation)
    events.on('task_run.after_call')(set_task_result)
    events.on('task_run.state_transition')(transition_state)
    events.on('task_run.heartbeat')(set_heartbeat)


@beartype
async def initialize_task_run_state(task_run: FilamentTaskRun) -> None:
    # lock so that we're not interrupted if initialize_task_run_state is called concurrently
    task_type_semaphore = RedisSemaphore(
        name=f'filament_task_type:initialize_task_run_state:{task_run.type.func_address}', max_leases=1, ttl=60
    )
    task_run_semaphore = RedisSemaphore(
        name=f'filament_task_run:initialize_task_run_state:{task_run.uuid}', max_leases=1, ttl=60
    )
    async with task_type_semaphore:
        async with async_session_scope() as session:
            task_type_statement = select(TaskType).where(TaskType.func_address == task_run.type.func_address)
            task_type_row = (await session.execute(task_type_statement)).scalars().one_or_none()
            if task_type_row is None:
                task_type_row = await upsert_task_type_state(session, task_run.type)
    async with task_run_semaphore:
        async with async_session_scope() as session:
            task_run_statement = select(TaskRun).where(TaskRun.task_uuid == task_run.uuid)
            task_run_row = (await session.execute(task_run_statement)).scalars().one_or_none()
            if task_run_row is None:
                task_run_row = await create_task_run_state(session=session, task_run=task_run)
                parent_task_run = peek_task_run()
                if parent_task_run is not None:
                    task_run_row.parent_task_uuid = parent_task_run.uuid


@beartype
async def listen_for_task_cancelled(task_uuid: str, cancel_scope: anyio.CancelScope) -> AsyncGenerator[bool, None]:
    while True:
        if await is_canceled(task_uuid):
            cancel_scope.cancel()
        await anyio.sleep(DEFAULT_MONITOR_INTERVAL)


@beartype
async def monitor_task_cancellation(task_run: FilamentTaskRun, task_group: anyio.TaskGroup) -> None:
    task_group.start_soon(listen_for_task_cancelled, task_run.uuid, task_group.cancel_scope)
