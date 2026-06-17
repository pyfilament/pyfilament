import functools
import inspect
import logging

from filament.logic.call_stack import peek_task_run
from filament.logic.events import EventManager
from filament.queue.types.remote_task_type import FilamentRemoteTaskType
from filament.registry.task_type_registry import register as register_task_type
from filament.state.register import register_task_events


def get_logger():
    task_run = peek_task_run()
    if task_run is not None:
        return logging.getLogger(f'{task_run.type.func_address}:{task_run.uuid}')
    # no task found, return a default logger for the caller
    parent_frame = inspect.currentframe().f_back
    parent_frame_module_name = parent_frame.f_globals.get('__name__', 'unknown')
    parent_frame_func_name = parent_frame.f_code.co_name
    return logging.getLogger(f'{parent_frame_module_name}:{parent_frame_func_name}')


def task(*wrapper_args, **wrapper_kwargs):
    func = None
    if len(wrapper_args) == 1 and callable(wrapper_args[0]):
        func = wrapper_args[0]

    def get_wrapper(
        func,
        **wrapper_kwargs,
    ):
        events = EventManager()
        register_task_events(events)
        task_type = FilamentRemoteTaskType(func, events=events, **wrapper_kwargs)
        register_task_type(task_type)
        return task_type

    get_wrapper = functools.partial(get_wrapper, **wrapper_kwargs)
    if func is not None:
        return get_wrapper(func)
    return get_wrapper
