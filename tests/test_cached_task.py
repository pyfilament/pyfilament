from filament.types.task_type import FilamentTaskType

_run_count = 0


def _task(func):
    task_type = FilamentTaskType(func, cache=True)
    return task_type


@_task
async def _run_parent():
    global _run_count
    _run_count += 1
    return f'parent, {_run_count}'


async def test_task():
    result = await _run_parent(refresh_cache=True)
    assert result == 'parent, 1'
    result = await _run_parent()
    assert result == 'parent, 1'
    result = await _run_parent(refresh_cache=True)
    assert result == 'parent, 2'
