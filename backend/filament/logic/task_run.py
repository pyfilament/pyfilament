from filament.db_models import TaskRun, TaskState
from filament.task_state import transition_state


def cancel_task_run(task_run: TaskRun) -> TaskRun:
    if task_run.state in TaskState.TERMINAL:
        return task_run
    transition_state(task_run.task_uuid, TaskState.CANCELLED)
    for child_task_run in task_run.child_tasks:
        cancel_task_run(child_task_run)
