import anyio

from filament.filament import task


@task
async def _run_parent():
    await anyio.sleep(0.1)
    child_task = await _run_child.request()
    result = await child_task
    await anyio.sleep(0.1)
    return f'parent, {result}'


@task
async def _run_child():
    await anyio.sleep(0.1)
    return 'child'


async def test_task():
    result = None

    async def _start_parent_task(shutdown_event: anyio.Event):
        nonlocal result
        result = await _run_parent()
        shutdown_event.set()

    async with anyio.create_task_group() as tg:
        shutdown_event = anyio.Event()
        tg.start_soon(_run_child.serve, shutdown_event)
        tg.start_soon(_start_parent_task, shutdown_event)

    assert result == 'parent, child'
