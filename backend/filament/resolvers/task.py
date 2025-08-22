import datetime

from strawberry import ID
from werkzeug.exceptions import BadRequest, NotFound

from filament.db_models import TaskRun as TaskRunModel
from filament.db_models import TaskType as TaskTypeModel
from filament.logic.task_run import cancel_task_run as logic_cancel_task_run
from filament.types.task import TaskRun, TaskType


async def get_task_run(self, info, id: ID | None = None, task_uuid: str | None = None) -> TaskRun:
    session = info.context['session']
    if task_uuid is not None:
        query = session.query(TaskRunModel).where(TaskRunModel.task_uuid == task_uuid)
    elif id is not None:
        query = session.query(TaskRunModel).where(TaskRunModel.id == id)
    else:
        raise BadRequest('Either id or task_uuid must be provided')
    task_run = query.one_or_none()
    if not task_run:
        raise NotFound(f'TaskRun with UUID {task_uuid} not found')
    return task_run


async def get_task_type(self, info, id: ID | None = None, func_address: str | None = None) -> TaskType:
    session = info.context['session']
    if func_address is not None:
        query = session.query(TaskTypeModel).where(TaskTypeModel.func_address == func_address)
    elif id is not None:
        query = session.query(TaskTypeModel).where(TaskTypeModel.id == id)
    else:
        raise BadRequest('Either id or func_address must be provided')
    task_type = query.one_or_none()
    if not task_type:
        raise NotFound(f'TaskType with func_address {func_address} not found')
    return task_type


async def get_task_types(self, info):
    session = info.context['session']
    today = datetime.datetime.now()
    before = today - datetime.timedelta(days=30)
    task_types = session.query(TaskTypeModel).join(TaskRunModel).filter(TaskRunModel.created_at > before).all()
    return task_types


async def cancel_task_run(self, info, id: ID | None = None, task_uuid: str | None = None) -> TaskRun:
    session = info.context['session']
    if task_uuid is not None:
        query = session.query(TaskRunModel).where(TaskRunModel.task_uuid == task_uuid)
    elif id is not None:
        query = session.query(TaskRunModel).where(TaskRunModel.id == id)
    else:
        raise BadRequest('Either id or task_uuid must be provided')
    task_run = query.one_or_none()
    if not task_run:
        raise NotFound(f'TaskRun with UUID {task_uuid} not found')
    logic_cancel_task_run(task_run)
    session.commit()
    return task_run


async def get_task_runs(self, info, task_type_id: ID, states: list[str] | None = None):
    session = info.context['session']
    query = session.query(TaskRunModel).where(TaskRunModel.task_type_id == task_type_id)
    if states:
        query = query.where(TaskRunModel.state.in_(states))
    task_runs = query.order_by(TaskRunModel.created_at.desc()).limit(99).all()
    return task_runs
