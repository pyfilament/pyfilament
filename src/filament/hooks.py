import logging

from beartype import beartype
from sqlalchemy import select

from filament.db_models import TaskRun
from filament.db_session import async_session_scope
from filament.filament import FilamentTaskRun
from filament.logic.func_registry import get_registered_entries
from filament.task.task_run import cancel_task_run
from filament.redis.semaphore import RedisSemaphore
from filament.task.task_state import create_task_type_state
from filament.logic.call_stack import peek_task_run

logger = logging.getLogger(__name__)


@beartype
async def create_all_task_type_states() -> None:
    semaphore = RedisSemaphore(name='filament_task_type:create_all', max_leases=1, ttl=60)
    async with semaphore:
        async with async_session_scope() as session:
            for func_entry in get_registered_entries():
                await create_task_type_state(session, func_entry)


@beartype
def get_current_task_run() -> FilamentTaskRun:
    task_run = peek_task_run()
    if task_run is not None:
        return task_run
    raise RuntimeError('No task found in stack')


@beartype
async def cancel_task_run_by_uuid(task_uuid: str) -> None:
    async with async_session_scope() as session:
        statement = select(TaskRun).where(TaskRun.task_uuid == task_uuid)
        task_run = (await session.execute(statement)).scalars().one_or_none()
        if task_run is not None:
            await cancel_task_run(session, task_run)
        else:
            logger.warning(f'TaskRun with UUID {task_uuid} not found')
