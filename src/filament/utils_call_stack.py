from contextvars import ContextVar

from beartype.typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from filament.filament import FilamentTaskRun

call_stack = ContextVar[list['FilamentTaskRun']]('filament.utils_call_stack:call_stack', default=[])


# @beartype # can't beartype here because circular import, fix later
def push_task_run(task_run: 'FilamentTaskRun'):
    current_stack = call_stack.get()
    new_stack = current_stack + [task_run]
    call_stack.set(new_stack)


# @beartype
def pop_task_run():
    current_stack = call_stack.get()
    if len(current_stack) > 0:
        new_stack = current_stack[:-1]
        call_stack.set(new_stack)


# @beartype
def peek_task_run() -> Optional['FilamentTaskRun']:
    current_stack = call_stack.get()
    if len(current_stack) == 0:
        return None
    return current_stack[-1]
