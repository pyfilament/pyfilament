import logging

from beartype import beartype

from filament.db_models import TaskRun
from filament.db_session import session_scope
from filament.func_registry import get_registered_entries
from filament.logic.task_run import cancel_task_run
from filament.redis_semaphore import RedisSemaphore
from filament.task_state import create_task_type_state
from filament.utils_call_stack import peek_task_run

logger = logging.getLogger(__name__)


@beartype
async def create_all_task_type_states() -> None:
    semaphore = RedisSemaphore(name='filament_task_type:create_all', max_leases=1, ttl=60)
    async with semaphore:
        with session_scope() as session:
            for func_entry in get_registered_entries():
                await create_task_type_state(session, func_entry)


def get_current_task_run():
    task_run = peek_task_run()
    if task_run is not None:
        return task_run
    raise RuntimeError('No task found in stack')


def cancel_task_run_by_uuid(task_uuid: str):
    with session_scope() as session:
        query = session.query(TaskRun).where(TaskRun.task_uuid == task_uuid)
        task_run = query.one_or_none()
        if task_run is not None:
            cancel_task_run(task_run)
        else:
            logger.warning(f'TaskRun with UUID {task_uuid} not found')
