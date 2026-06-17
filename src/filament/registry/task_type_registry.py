from typing import TYPE_CHECKING

from beartype import beartype

if TYPE_CHECKING:
    from filament.types.task_type import FilamentTaskType
else:
    FilamentTaskType = 'filament.types.task_type.FilamentTaskType'

__TASK_TYPE_REGISTRY = {}


@beartype
def _get_task_type_registry() -> dict[str, FilamentTaskType]:
    return __TASK_TYPE_REGISTRY


@beartype
def register(task_type: FilamentTaskType) -> None:
    registry = _get_task_type_registry()
    registry[task_type.func_address] = task_type


@beartype
def lookup(task_address: str):
    registry = _get_task_type_registry()
    if task_address not in registry:
        module_name, func_name = task_address.split(':')
        __import__(module_name, fromlist=[func_name])
    assert task_address in registry, f'Task {task_address} not found'
    return registry.get(task_address)


@beartype
def print_task_registry() -> None:
    registry = _get_task_type_registry()
    print(registry.keys())
