from beartype import beartype

TASK_TYPE_REGISTRY = {}


@beartype
def register(task_type: 'filament.task.types.task_type.FilamentTaskType') -> None:
    TASK_TYPE_REGISTRY[task_type.func_address] = task_type


@beartype
def lookup(task_address: str):
    if task_address not in TASK_TYPE_REGISTRY:
        module_name, func_name = task_address.split(':')
        __import__(module_name, fromlist=[func_name])
    assert task_address in TASK_TYPE_REGISTRY, f'Task {task_address} not found'
    return TASK_TYPE_REGISTRY.get(task_address)


@beartype
def print_task_registry() -> None:
    print(TASK_TYPE_REGISTRY.keys())
