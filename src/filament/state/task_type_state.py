import inspect
import json
from types import NoneType
from typing import TYPE_CHECKING

from beartype import beartype
from beartype.door import TypeHint, UnionTypeHint
from beartype.typing import Any, Optional
from inflection import camelize
from pydantic import BaseModel, ConfigDict, TypeAdapter, create_model
from pydantic.errors import PydanticInvalidForJsonSchema, PydanticSchemaGenerationError, PydanticUserError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament.db.models import TaskType
from filament.state.common import with_session

if TYPE_CHECKING:
    from filament.types.task_type import FilamentTaskType
else:
    FilamentTaskType = 'filament.types.task_type.FilamentTaskType'


@with_session
@beartype
async def upsert_task_type_state(session: AsyncSession, task_type: FilamentTaskType) -> None:
    name = task_type.func_address
    input_json_schema = _get_parameters_spec(task_type, name)
    output_json_schema = _get_result_spec(task_type)
    statement = select(TaskType).where(TaskType.func_address == task_type.func_address)
    task_type_row = (await session.execute(statement)).scalars().one_or_none()
    if task_type_row is not None:
        if task_type.name != name:
            task_type_row.name = name
        if task_type_row.parameters_spec != input_json_schema:
            task_type_row.parameters_spec = input_json_schema
        if task_type_row.result_spec != output_json_schema:
            task_type_row.result_spec = output_json_schema
    else:
        task_type_row = TaskType(
            name=name,
            func_address=task_type.func_address,
            parameters_spec=input_json_schema,
            result_spec=output_json_schema,
        )
        session.add(task_type_row)


@beartype
def _get_result_spec(task_type: FilamentTaskType) -> str | None:
    signature = inspect.signature(task_type._func)
    if signature.return_annotation != inspect.Signature.empty:
        output_format = signature.return_annotation
        if isinstance(output_format, type) and issubclass(output_format, BaseModel):
            try:
                return json.dumps(signature.return_annotation.model_json_schema(), separators=(',', ':'), default=str)
            except PydanticInvalidForJsonSchema:
                return None
    return None


@beartype
def _get_parameters_spec(task_type: FilamentTaskType, func_name: str | None = None) -> str | None:
    func = task_type._func
    signature = inspect.signature(func)
    allowed_types = {}
    for param_name, param in signature.parameters.items():
        is_required = param.default == param.empty
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        allowed_type = None
        if param.annotation != inspect.Signature.empty:
            input_type = param.annotation
            if _is_pydantic_compatible(input_type):
                allowed_type = input_type
        if allowed_type is not None:
            if is_required:
                allowed_types[param_name] = allowed_type
            elif _is_optional(allowed_type):
                allowed_types[param_name] = allowed_type
            else:
                allowed_types[param_name] = Optional[allowed_type]
        elif is_required:
            return None

    if func_name is None:
        func_name = func.__name__

    InputModel = create_model(
        f'{camelize(func_name)}InputModel',
        __config__=ConfigDict(use_attribute_docstrings=True, extra='forbid'),
        **allowed_types,
    )

    try:
        return json.dumps(InputModel.model_json_schema(), separators=(',', ':'), default=str)
    except PydanticInvalidForJsonSchema:
        return None
    except PydanticUserError:
        return None


@beartype
def _is_pydantic_compatible(type_: Any) -> bool:
    try:
        TypeAdapter(type_)
        return True
    except PydanticSchemaGenerationError:
        return False


@beartype
def _is_optional(type_: Any) -> bool:
    hint = TypeHint(type_)
    return isinstance(hint, UnionTypeHint) and NoneType in hint.args
