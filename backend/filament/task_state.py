import json
import logging

from sqlmodel import Session, create_engine, select

from filament.db_models import TaskRun, TaskRunStateTransition, TaskState, TaskType, engine, get_utc_now
from filament.utils import json_encode_safe

logger = logging.getLogger(__name__)


REDIS_KEY_PREFIX = 'task_run:'


def get_key(key):
    return f'{REDIS_KEY_PREFIX}{key}'


def set_heartbeat(task_uuid):
    # task_run = TaskRun.model_validate_json(r_sync.get(get_key(task_uuid)))
    # task_run.heartbeat = time.time()
    # r_sync.set(get_key(task_uuid), task_run.model_dump_json())
    with Session(engine) as session:
        statement = select(TaskRun).where(TaskRun.task_uuid == task_uuid)
        task_run = session.exec(statement).one()
        task_run.heartbeat = get_utc_now()
        session.commit()
    # print(f"{now()} {task_run} heartbeat")


def create_task_type_state(func_address, name=None):
    with Session(engine) as session:
        statement = select(TaskType).where(TaskType.func_address == func_address)
        task_type = session.exec(statement).first()
        if task_type is not None:
            task_type.name = name
        else:
            task_type = TaskType(name=name, func_address=func_address)
            session.add(task_type)
        session.commit()
    return task_type


def create_task_run_state(task_uuid, func_address, name=None, parameters=None):
    with Session(engine) as session:
        statement = select(TaskType).where(TaskType.func_address == func_address)
        task_type = session.exec(statement).one()
        if task_type is None:
            raise ValueError(f'No task type found for func_address {func_address}')
        task_run = TaskRun(name=name, task_uuid=task_uuid, task_type_id=task_type.id)
        if parameters is not None:
            task_run.parameters_json = json.dumps(json_encode_safe(parameters), separators=(',', ':'), default=str)
        # r_sync.set(get_key(task_uuid), task_run.model_dump_json())
        session.add(task_run)
        session.commit()
    # logger.info(f"{task_run} created")
    return task_run


def transition_state(task_uuid, new_state):
    with Session(engine) as session:
        # task_run = TaskRun.model_validate_json(r_sync.get(get_key(task_uuid)))
        statement = select(TaskRun).where(TaskRun.task_uuid == task_uuid)
        task_run = session.exec(statement).one()
        old_state = task_run.state
        if old_state == new_state:
            # logger.info(f'{task_run} already in state {new_state}')
            return
        if new_state == TaskState.RUNNING:
            task_run.run_count += 1
        task_run.state = new_state
        task_run.state_since = get_utc_now()
        transition = TaskRunStateTransition(
            task_uuid=task_uuid, from_state=old_state, to_state=new_state, state_since=task_run.state_since
        )
        session.add(transition)
        # logger.info(f'{task_run} from {old_state} to {new_state}')
        # r_sync.set(get_key(task_uuid), task_run.model_dump_json())
        session.commit()


def set_task_result(task_uuid, result, exception):
    with Session(engine) as session:
        statement = select(TaskRun).where(TaskRun.task_uuid == task_uuid)
        task_run = session.exec(statement).one()
        if exception is not None:
            result = exception
        task_run.result_json = json.dumps(json_encode_safe(result), separators=(',', ':'), default=str)
        session.commit()


def get_task_run(task_uuid):
    with Session(engine) as session:
        statement = select(TaskRun).where(TaskRun.task_uuid == task_uuid)
        task_run = session.exec(statement).one()
        return task_run.model_dump()


def is_canceled(task_uuid):
    # task_run = TaskRun.model_validate_json(r_sync.get(get_key(task_uuid)))
    # if task_run.state == TaskState.CANCELLED:
    #     return True
    # return False
    with Session(engine) as session:
        statement = select(TaskRun).where(TaskRun.task_uuid == task_uuid)
        task_run = session.exec(statement).one()
        return task_run.state == TaskState.CANCELLED


def set_parent_task_uuid(task_uuid, parent_task_uuid):
    # logger.info(f"{task_uuid} set parent_task_uuid to {parent_task_uuid}")
    # task_data = r_sync.get(get_key(task_uuid))
    # task_run = TaskRun.model_validate_json(task_data)
    # task_run.parent_task_uuid = parent_task_uuid
    # r_sync.set(get_key(task_uuid), task_run.model_dump_json())
    with Session(engine) as session:
        statement = select(TaskRun).where(TaskRun.task_uuid == task_uuid)
        task_run = session.exec(statement).one()
        task_run.parent_task_uuid = parent_task_uuid
        session.commit()
