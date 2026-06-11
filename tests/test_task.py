import anyio

from filament.task.types.task_type import FilamentTaskType


def _task(func):
    task_type = FilamentTaskType(func)
    return task_type


@_task
async def _run_parent():
    await anyio.sleep(0.1)
    result = await _run_child()
    await anyio.sleep(0.1)
    return f'parent, {result}'


@_task
async def _run_child():
    await anyio.sleep(0.1)
    return 'child'


async def test_task():
    result = await _run_parent()
    assert result == 'parent, child'
