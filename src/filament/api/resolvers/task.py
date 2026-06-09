import datetime
import json

from sqlalchemy import select
from sqlalchemy.orm import aliased
from sqlalchemy.sql import func
from strawberry import ID, Info
from werkzeug.exceptions import BadRequest, NotFound

from filament.db_models import TaskRun as TaskRunModel
from filament.db_models import TaskType as TaskTypeModel
from filament.task.task_run import cancel_task_run as logic_cancel_task_run
from filament.task.task_type_registry import lookup
from filament.types.task import TaskRun, TaskType

DEFAULT_MAX_DAYS = 3


async def get_task_run(self, info: Info, id: ID | None = None, task_uuid: str | None = None) -> TaskRun:
    session = info.context['session']
    if task_uuid is not None:
        statement = select(TaskRunModel).where(TaskRunModel.task_uuid == task_uuid)
    elif id is not None:
        statement = select(TaskRunModel).where(TaskRunModel.id == int(id))
    else:
        raise BadRequest('Either id or task_uuid must be provided')
    task_run = (await session.execute(statement)).scalars().one_or_none()
    if not task_run:
        raise NotFound(f'TaskRun with ID {id} or UUID {task_uuid} not found')
    return task_run


async def get_task_type(self, info: Info, id: ID | None = None, func_address: str | None = None) -> TaskType:
    session = info.context['session']
    if func_address is not None:
        statement = select(TaskTypeModel).where(TaskTypeModel.func_address == func_address)
    elif id is not None:
        statement = select(TaskTypeModel).where(TaskTypeModel.id == int(id))
    else:
        raise BadRequest('Either id or func_address must be provided')
    task_type = (await session.execute(statement)).scalars().one_or_none()
    if not task_type:
        raise NotFound(f'TaskType with id {id} or func_address {func_address} not found')
    return task_type


async def get_task_types_by_ids(
    self, info: Info, ids: list[int] | None = None, uuids: list[str] | None = None
) -> list[TaskType]:
    session = info.context['session']
    if ids:
        statement = select(TaskTypeModel).where(TaskTypeModel.id.in_(ids))
        task_types = (await session.execute(statement)).scalars().all()
        ids_to_task_types = {task_type.id: task_type for task_type in task_types}
        task_types = [ids_to_task_types[id] for id in ids if id in ids_to_task_types]
    elif uuids:
        statement = select(TaskTypeModel).where(TaskTypeModel.uuid.in_(uuids))
        task_types = (await session.execute(statement)).scalars().all()
        uuids_to_task_types = {task_type.uuid: task_type for task_type in task_types}
        task_types = [uuids_to_task_types[uuid] for uuid in uuids if uuid in uuids_to_task_types]
    else:
        raise BadRequest('Either ids or uuids must be provided')
    return task_types


async def get_task_type_stack_runs(
    self, info: Info, task_type_ids: list[int], states: list[str] | None = None
) -> list[TaskRun]:
    session = info.context['session']
    if len(task_type_ids) == 0:
        raise BadRequest('task_type_ids must be provided')
    MAX_RESULTS = 100
    final_task_type_id = task_type_ids[-1]
    statement = select(TaskRunModel).filter(TaskRunModel.task_type_id == final_task_type_id)
    if states:
        statement = statement.where(TaskRunModel.state.in_(states))
    last_model = TaskRunModel
    for task_type_id in reversed(task_type_ids[:-1]):
        current_model = aliased(TaskRunModel)
        statement = statement.join(current_model, last_model.parent_task_uuid == current_model.task_uuid)
        statement = statement.where(current_model.task_type_id == task_type_id)
        last_model = current_model
    statement = (
        statement.where(last_model.parent_task_uuid.is_(None))
        .order_by(TaskRunModel.created_at.desc())
        .limit(MAX_RESULTS)
    )
    task_runs = (await session.execute(statement)).scalars().all()
    return task_runs


async def get_task_runs_by_ids(self, info: Info, ids: list[int]) -> list[TaskRun]:
    session = info.context['session']
    if len(ids) == 0:
        raise BadRequest('ids must be provided')
    statement = select(TaskRunModel).where(TaskRunModel.id.in_(ids))
    task_runs = (await session.execute(statement)).scalars().all()
    ids_to_task_runs = {task_run.id: task_run for task_run in task_runs}
    for id in ids:
        if id not in ids_to_task_runs:
            raise NotFound(f'TaskRun with ID {id} not found')
    task_runs = [ids_to_task_runs[id] for id in ids if id in ids_to_task_runs]
    return task_runs


async def get_task_types(self, info: Info, days: int = DEFAULT_MAX_DAYS):
    session = info.context['session']
    today = datetime.datetime.now()
    before = today - datetime.timedelta(days=days)
    subquery = (
        select(TaskRunModel.task_type_id, func.max(TaskRunModel.id).label('task_run_id'))
        .filter(TaskRunModel.created_at > before)
        .group_by(TaskRunModel.task_type_id)
        .subquery()
    )
    task_types_statement = select(TaskTypeModel).join(
        subquery,
        TaskTypeModel.id == subquery.c.task_type_id,
    )
    task_types = (await session.execute(task_types_statement)).scalars().all()
    return task_types


async def cancel_task_run(self, info: Info, id: ID | None = None, task_uuid: str | None = None) -> TaskRun:
    session = info.context['session']
    if task_uuid is not None:
        statement = select(TaskRunModel).where(TaskRunModel.task_uuid == task_uuid)
    elif id is not None:
        statement = select(TaskRunModel).where(TaskRunModel.id == int(id))
    else:
        raise BadRequest('Either id or task_uuid must be provided')
    task_run = (await session.execute(statement)).scalars().one_or_none()
    if not task_run:
        raise NotFound(f'TaskRun with UUID {task_uuid} not found')
    await logic_cancel_task_run(session, task_run)
    return task_run


async def get_task_runs(
    self, info: Info, task_type_id: ID, states: list[str] | None = None, days: int = DEFAULT_MAX_DAYS
):
    session = info.context['session']
    today = datetime.datetime.now()
    before = today - datetime.timedelta(days=days)
    statement = (
        select(TaskRunModel)
        .where(TaskRunModel.task_type_id == int(task_type_id))
        .where(TaskRunModel.created_at > before)
    )
    if states:
        statement = statement.where(TaskRunModel.state.in_(states))
    statement = statement.order_by(TaskRunModel.created_at.desc()).limit(99)
    task_runs = (await session.execute(statement)).scalars().all()
    return task_runs


async def run_task(self, info: Info, task_type_id: ID, parameters_json: str) -> TaskRun:
    session = info.context['session']
    statement = select(TaskTypeModel).where(TaskTypeModel.id == int(task_type_id))
    task_type = (await session.execute(statement)).scalars().one()
    func_address = task_type.func_address
    filament_task_type = lookup(func_address)
    parameters = json.loads(parameters_json)
    parameters.update({'start_immediately': True})
    filament_task_run = await filament_task_type._request(task_args=[], task_kwargs=parameters)
    statement = select(TaskRunModel).where(TaskRunModel.task_uuid == filament_task_run.uuid)
    task_run = (await session.execute(statement)).scalars().one()
    return task_run
