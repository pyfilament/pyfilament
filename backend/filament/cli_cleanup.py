import logging
import sys
from datetime import datetime, timedelta, timezone
from functools import partial, wraps

import anyio
import fire

from filament.db_models import TaskRun, TaskState
from filament.db_session import session_scope
from filament.logic.task_run import cancel_task_run


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
async def main(stonith_max_heartbeat_seconds: int = 60 * 60):
    await stonith(max_heartbeat_seconds=stonith_max_heartbeat_seconds)


async def stonith(max_heartbeat_seconds: int, batch_size: int = 100):
    with session_scope() as session:
        while True:
            now = datetime.now(timezone.utc)
            heartbeat_threshold = now - timedelta(seconds=max_heartbeat_seconds)
            task_runs = (
                session.query(TaskRun)
                .filter(~TaskRun.state.in_(TaskState.TERMINAL))
                .filter(TaskRun.heartbeat < heartbeat_threshold)
                .order_by(TaskRun.heartbeat.desc())
                .limit(batch_size)
                .all()
            )
            logger.info(f'Found {len(task_runs)} task runs to STONITH')
            any_age = None
            for task_run in task_runs:
                heartbeat_age = now - task_run.heartbeat
                logger.debug(f'Cancelling task run {task_run.id} heartbeat_age={heartbeat_age}')
                if any_age is None:
                    any_age = heartbeat_age
                cancel_task_run(task_run)
                session.flush()
            session.commit()
            logger.info(f'STONITHed {len(task_runs)} task runs, any heartbeat_age={any_age}')
            await anyio.sleep(1)
            if len(task_runs) < batch_size:
                break


if __name__ == '__main__':
    fire.Fire(main)
