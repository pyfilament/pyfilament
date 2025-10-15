import datetime
import json

from sqlalchemy.orm import aliased
from strawberry import ID
from werkzeug.exceptions import BadRequest, NotFound

from filament.db_models import TaskRun as TaskRunModel
from filament.db_models import TaskType as TaskTypeModel
from filament.filament import lookup
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
        raise NotFound(f'TaskRun with ID {id} or UUID {task_uuid} not found')
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
        raise NotFound(f'TaskType with id {id} or func_address {func_address} not found')
    return task_type


async def get_task_types_by_ids(
    self, info, ids: list[int] | None = None, uuids: list[str] | None = None
) -> list[TaskType]:
    session = info.context['session']
    if ids:
        task_types = session.query(TaskTypeModel).where(TaskTypeModel.id.in_(ids)).all()
        ids_to_task_types = {task_type.id: task_type for task_type in task_types}
        task_types = [ids_to_task_types[id] for id in ids if id in ids_to_task_types]
    elif uuids:
        task_types = session.query(TaskTypeModel).where(TaskTypeModel.uuid.in_(uuids)).all()
        uuids_to_task_types = {task_type.uuid: task_type for task_type in task_types}
        task_types = [uuids_to_task_types[uuid] for uuid in uuids if uuid in uuids_to_task_types]
    else:
        raise BadRequest('Either ids or uuids must be provided')
    return task_types


async def get_task_type_stack_runs(
    self, info, task_type_ids: list[int], states: list[str] | None = None
) -> list[TaskRun]:
    session = info.context['session']
    if len(task_type_ids) == 0:
        raise BadRequest('task_type_ids must be provided')
    MAX_RESULTS = 100
    final_task_type_id = task_type_ids[-1]
    query = session.query(TaskRunModel).filter(TaskRunModel.task_type_id == final_task_type_id)
    if states:
        query = query.where(TaskRunModel.state.in_(states))
    last_model = TaskRunModel
    for task_type_id in reversed(task_type_ids[:-1]):
        current_model = aliased(TaskRunModel)
        query = query.join(current_model, last_model.parent_task_uuid == current_model.task_uuid)
        query = query.where(current_model.task_type_id == task_type_id)
        last_model = current_model
    task_runs = (
        query.where(last_model.parent_task_uuid.is_(None))
        .order_by(TaskRunModel.created_at.desc())
        .limit(MAX_RESULTS)
        .all()
    )
    return task_runs


async def get_task_runs_by_ids(self, info, ids: list[int]) -> list[TaskRun]:
    session = info.context['session']
    if len(ids) == 0:
        raise BadRequest('ids must be provided')
    task_runs = []
    for id in ids:
        task_run = session.get(TaskRunModel, id)
        if task_run is None:
            raise NotFound(f'TaskRun with ID {id} not found')
        task_runs.append(task_run)
    return task_runs


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


async def run_task(self, info, task_type_id: ID, parameters_json: str) -> TaskRun:
    session = info.context['session']
    task_type = session.query(TaskTypeModel).where(TaskTypeModel.id == task_type_id).one()
    func_address = task_type.func_address
    filament_task_type = lookup(func_address)
    parameters = json.loads(parameters_json)
    parameters.update({'start_immediately': True})
    filament_task_run = filament_task_type._request(task_args=[], task_kwargs=parameters)
    task_run = session.query(TaskRunModel).where(TaskRunModel.task_uuid == filament_task_run.uuid).one()
    return task_run
