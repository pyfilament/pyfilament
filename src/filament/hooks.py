import logging

from beartype import beartype
from sqlalchemy import select

from filament.db.models import TaskRun
from filament.db.session import async_session_scope
from filament.logic.call_stack import peek_task_run
from filament.state.task_run_state import cancel_task_run
from filament.types.task_run import FilamentTaskRun

logger = logging.getLogger(__name__)


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
