import anyio
import mock
from filament.types.task_type import FilamentTaskType

from filament.hooks import cancel_task_run_by_uuid
from filament.logic.events import EventManager
from filament.state.register import register_task_events


def _task(func):
    events = EventManager()
    register_task_events(events)
    task_type = FilamentTaskType(func, events=events)
    return task_type


_global_state = {'parent_set': False, 'child_set': False}


@_task
async def _run_parent():
    await anyio.sleep(0.5)
    _global_state['parent_set'] = True
    result = await _run_child()
    await anyio.sleep(0.1)
    return f'parent, {result}'


@_task
async def _run_child():
    await anyio.sleep(0.5)
    _global_state['child_set'] = True
    return 'child'


@mock.patch('filament.state.register.DEFAULT_MONITOR_INTERVAL', 0.02)
async def test_cancel():
    parent_task = None

    async def _cancel_parent_task():
        nonlocal parent_task
        await anyio.sleep(0.75)
        assert parent_task is not None, 'Parent task not started'
        await cancel_task_run_by_uuid(parent_task.uuid)

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
        tg.start_soon(_start_parent_task, shutdown_event)
        tg.start_soon(_cancel_parent_task)

    assert _global_state['parent_set']
    assert not _global_state['child_set']
