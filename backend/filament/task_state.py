import inspect
import json
import logging
from types import NoneType
from typing import Any, Callable, Optional

import pydantic
from beartype import beartype
from beartype.door import TypeHint, UnionTypeHint
from inflection import camelize
from sqlalchemy.orm import Session

from filament.db_models import TaskRun, TaskRunStateTransition, TaskState, TaskType, get_utc_now
from filament.db_session import session_scope
from filament.func_registry import FuncRegistryEntry
from filament.utils import get_json_dict, json_encode_safe

logger = logging.getLogger(__name__)


REDIS_KEY_PREFIX = 'task_run:'


@beartype
def with_session(func: Callable) -> Callable:
    if inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func):

        async def wrapper(*args, **kwargs):
            if ('session' in kwargs and kwargs['session'] is not None) or (
                len(args) > 0 and isinstance(args[0], Session)
            ):
                return await func(*args, **kwargs)
            else:
                with session_scope() as session:
                    return await func(session, *args, **kwargs)
    else:

        def wrapper(*args, **kwargs):
            if ('session' in kwargs and kwargs['session'] is not None) or (
                len(args) > 0 and isinstance(args[0], Session)
            ):
                return func(*args, **kwargs)
            else:
                with session_scope() as session:
                    return func(session, *args, **kwargs)

    return wrapper


@beartype
def get_key(key: str) -> str:
    return f'{REDIS_KEY_PREFIX}{key}'


@beartype
@with_session
def set_heartbeat(session: Session, task_uuid: str) -> None:
    query = session.query(TaskRun).where(TaskRun.task_uuid == task_uuid)
    task_run = query.one()
    task_run.heartbeat = get_utc_now()


@beartype
@with_session
async def create_task_type_state(session: Session, func_entry: FuncRegistryEntry, name: str | None = None) -> None:
    input_json_schema = get_parameters_spec(func_entry, name)
    output_json_schema = get_result_spec(func_entry)
    query = session.query(TaskType).where(TaskType.func_address == func_entry.func_address)
    task_type = query.one_or_none()
    if task_type is not None:
        if name is not None:
            task_type.name = name
        if task_type.parameters_spec != input_json_schema:
            task_type.parameters_spec = input_json_schema
        if task_type.result_spec != output_json_schema:
            task_type.result_spec = output_json_schema
    else:
        task_type = TaskType(
            name=name,
            func_address=func_entry.func_address,
            parameters_spec=input_json_schema,
            result_spec=output_json_schema,
        )
        session.add(task_type)


@beartype
def is_pydantic_compatible(type_: Any) -> bool:
    try:
        pydantic.TypeAdapter(type_)
        return True
    except pydantic.errors.PydanticTypeError:
        return False


@beartype
def is_optional(type_: Any) -> bool:
    hint = TypeHint(type_)
    return isinstance(hint, UnionTypeHint) and NoneType in hint.args


@beartype
def get_parameters_spec(func_entry: FuncRegistryEntry, func_name: str | None = None) -> str | None:
    func, class_ = func_entry.func, func_entry.class_
    signature = inspect.signature(func)
    allowed_types = {}
    for param_name, param in signature.parameters.items():
        is_required = param.default == param.empty
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        allowed_type = None
        if param_name == 'self' and isinstance(class_, type) and issubclass(class_, pydantic.BaseModel):
            allowed_type = class_
        if param.annotation != inspect.Signature.empty:
            input_type = param.annotation
            if is_pydantic_compatible(input_type):
                allowed_type = input_type
        if allowed_type is not None:
            if is_required:
                allowed_types[param_name] = allowed_type
            elif is_optional(allowed_type):
                allowed_types[param_name] = allowed_type
            else:
                allowed_types[param_name] = Optional[allowed_type]
        elif is_required:
            return None

    if func_name is None:
        func_name = func.__name__

    InputModel = pydantic.create_model(
        f'{camelize(func_name)}InputModel',
        __config__=pydantic.ConfigDict(use_attribute_docstrings=True, extra='forbid'),
        **allowed_types,
    )

    try:
        return json.dumps(InputModel.model_json_schema(), separators=(',', ':'), default=str)
    except pydantic.errors.PydanticInvalidForJsonSchema:
        return None


@beartype
def get_result_spec(func_entry: FuncRegistryEntry) -> str | None:
    signature = inspect.signature(func_entry.func)
    if signature.return_annotation != inspect.Signature.empty:
        output_format = signature.return_annotation
        if isinstance(output_format, type) and issubclass(output_format, pydantic.BaseModel):
            try:
                return json.dumps(signature.return_annotation.model_json_schema(), separators=(',', ':'), default=str)
            except pydantic.errors.PydanticInvalidForJsonSchema:
                return None
    return None


@beartype
@with_session
def create_task_run_state(
    session: Session, task_uuid: str, func_address: str, name: str | None = None, parameters: dict | None = None
) -> None:
    query = session.query(TaskType).where(TaskType.func_address == func_address)
    task_type = query.one_or_none()
    if task_type is None:
        raise ValueError(f'No task type found for func_address {func_address}')
    task_run = TaskRun(name=name, task_uuid=task_uuid, task_type_id=task_type.id)
    if parameters is not None:
        task_run.parameters_json = json.dumps(json_encode_safe(parameters), separators=(',', ':'), default=str)
    session.add(task_run)


@beartype
@with_session
def transition_state(session: Session, task_uuid: str, new_state: TaskState) -> None:
    query = session.query(TaskRun).where(TaskRun.task_uuid == task_uuid)
    task_run = query.one()
    old_state = task_run.state
    if old_state == new_state:
        return
    if new_state == TaskState.RUNNING:
        task_run.run_count += 1
    task_run.state = new_state
    task_run.state_since = get_utc_now()
    transition = TaskRunStateTransition(
        task_uuid=task_uuid, from_state=old_state, to_state=new_state, state_since=task_run.state_since
    )
    session.add(transition)


@beartype
@with_session
def set_task_result(session: Session, task_uuid: str, result: Any, exception: BaseException | None = None) -> None:
    query = session.query(TaskRun).where(TaskRun.task_uuid == task_uuid)
    task_run = query.one()
    if exception is not None:
        result = exception
    task_run.result_json = json.dumps(json_encode_safe(result), separators=(',', ':'), default=str)


@beartype
@with_session
async def get_task_run_dict(session: Session, task_uuid: str) -> dict:
    query = session.query(TaskRun).where(TaskRun.task_uuid == task_uuid)
    task_run = query.one()
    return get_json_dict(task_run)


@beartype
@with_session
def is_canceled(session: Session, task_uuid: str) -> bool:
    query = session.query(TaskRun).where(TaskRun.task_uuid == task_uuid)
    task_run = query.one()
    return task_run.state == TaskState.CANCELLED


@beartype
@with_session
def set_parent_task_uuid(session: Session, task_uuid: str, parent_task_uuid: str) -> None:
    query = session.query(TaskRun).where(TaskRun.task_uuid == task_uuid)
    task_run = query.one()
    task_run.parent_task_uuid = parent_task_uuid


@beartype
@with_session
def get_parent_task_uuid(session: Session, task_uuid: str) -> str | None:
    query = session.query(TaskRun).where(TaskRun.task_uuid == task_uuid)
    task_run = query.one_or_none()
    return task_run.parent_task_uuid if task_run else None
