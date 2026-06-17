from contextvars import ContextVar
from typing import TYPE_CHECKING

from beartype import beartype
from beartype.typing import Optional

if TYPE_CHECKING:
    from filament.types.task_run import FilamentTaskRun
else:
    FilamentTaskRun = 'filament.types.task_run.FilamentTaskRun'

_call_stack = None


@beartype
def _get_call_stack() -> ContextVar[list[FilamentTaskRun]]:
    global _call_stack
    if _call_stack is None:
        _call_stack = ContextVar('filament.logic._get_call_stack:_get_call_stack', default=[])
    return _call_stack


@beartype
def push_task_run(task_run: FilamentTaskRun):
    current_stack = _get_call_stack().get()
    new_stack = current_stack + [task_run]
    _get_call_stack().set(new_stack)


@beartype
def pop_task_run():
    current_stack = _get_call_stack().get()
    if len(current_stack) > 0:
        new_stack = current_stack[:-1]
        _get_call_stack().set(new_stack)


@beartype
def peek_task_run() -> Optional[FilamentTaskRun]:
    current_stack = _get_call_stack().get()
    if len(current_stack) == 0:
        return None
    return current_stack[-1]
