import logging
import sys
from datetime import datetime, timedelta, timezone
from functools import partial, wraps

import anyio
import fire
from sqlalchemy import select

from filament.db_models import TaskRun, TaskState
from filament.db_session import async_session_scope
from filament.logic.task_run import cancel_task_run, delete_task_run


def setup_logging():
    logger = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


setup_logging()

logger = logging.getLogger(__name__)


def fire_task(async_fn):
    @wraps(async_fn)
    def wrapper(*args, **kwargs):
        callback = partial(async_fn, *args, **kwargs)
        anyio.run(callback)

    return wrapper


@fire_task
async def main(stonith_max_heartbeat_seconds: int = 60 * 60, delete_old_task_runs_days: int = 30):
    await stonith(max_heartbeat_seconds=stonith_max_heartbeat_seconds)
    await delete_old_task_runs(days=delete_old_task_runs_days)


async def stonith(max_heartbeat_seconds: int, batch_size: int = 100):
    while True:
        async with async_session_scope() as session:
            now = datetime.now(timezone.utc)
            heartbeat_threshold = now - timedelta(seconds=max_heartbeat_seconds)
            task_runs_statement = (
                select(TaskRun)
                .where(~TaskRun.state.in_(TaskState.TERMINAL))
                .where(TaskRun.heartbeat < heartbeat_threshold)
                .order_by(TaskRun.heartbeat.desc())
                .limit(batch_size)
            )
            task_runs = (await session.execute(task_runs_statement)).scalars().all()
            logger.info(f'Found {len(task_runs)} task runs to STONITH')
            any_age = None
            for task_run in task_runs:
                heartbeat_age = now - task_run.heartbeat
                logger.debug(f'Cancelling task run {task_run.id} heartbeat_age={heartbeat_age}')
                if any_age is None:
                    any_age = heartbeat_age
                await cancel_task_run(session, task_run)
                await session.flush()
            await session.commit()
            logger.info(f'STONITHed {len(task_runs)} task runs, any heartbeat_age={any_age}')
            await anyio.sleep(1)
            if len(task_runs) < batch_size:
                break


async def delete_old_task_runs(days: int = 30, batch_size: int = 100):
    while True:
        async with async_session_scope() as session:
            statement = (
                select(TaskRun)
                .where(TaskRun.created_at < datetime.now(timezone.utc) - timedelta(days=days))
                .limit(batch_size)
            )
            task_runs = (await session.execute(statement)).scalars().all()
            logger.info(f'Found {len(task_runs)} task runs to delete')
            any_age = None
            for task_run in task_runs:
                await delete_task_run(session, task_run)
                if any_age is None:
                    any_age = task_run.created_at
            await session.commit()
            logger.info(f'Deleted {len(task_runs)} task runs, any_age={any_age}')
            await anyio.sleep(1)
            if len(task_runs) < batch_size:
                break


if __name__ == '__main__':
    fire.Fire(main)
