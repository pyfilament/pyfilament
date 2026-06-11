import anyio

from tests.test_queue import _task

_global_state = {'parent_set': False, 'child_set': False}


@_task
async def _run_parent():
    await anyio.sleep(0.1)
    _global_state['parent_set'] = True
    child_task = await _run_child.request()
    result = await child_task
    await anyio.sleep(0.1)
    return f'parent, {result}'


@_task
async def _run_child():
    await anyio.sleep(0.1)
    _global_state['child_set'] = True
    return 'child'


async def test_cancel():
    parent_task = None

    async def _cancel_parent_task():
        nonlocal parent_task
        await anyio.sleep(0.15)
        assert parent_task is not None, 'Parent task not started'
        parent_task.cancel()

    async def _start_parent_task(shutdown_event: anyio.Event):
        nonlocal parent_task
        parent_task = _run_parent()
        try:
            await parent_task
        except anyio.get_cancelled_exc_class():
            pass
        finally:
            shutdown_event.set()

    async with anyio.create_task_group() as tg:
        shutdown_event = anyio.Event()
        tg.start_soon(_run_child.serve, shutdown_event)
        tg.start_soon(_start_parent_task, shutdown_event)
        tg.start_soon(_cancel_parent_task)

    assert _global_state['parent_set']
    assert not _global_state['child_set']
