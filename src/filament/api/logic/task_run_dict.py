from beartype import beartype

from filament.db_models import TaskRun as TaskRunModel
from filament.utils import avoid_nans, get_json_dict


@beartype
async def deep_get_task_run_dict(task_run: TaskRunModel, max_child_tasks: int = 100, child_depth: int = 0) -> dict:
    task_run_dict = get_json_dict(task_run)
    task_run_dict['task_type'] = get_json_dict(await task_run.awaitable_attrs.task_type)
    if child_depth > 0:
        sorted_child_tasks = sorted(await task_run.awaitable_attrs.child_tasks, key=lambda x: x.id)
        task_run_dict['child_tasks'] = [
            await deep_get_task_run_dict(child_task_run, max_child_tasks, child_depth - 1)
            for child_task_run in sorted_child_tasks[:max_child_tasks]
        ]
    else:
        task_run_dict['child_tasks'] = []
    sorted_state_transitions = sorted(await task_run.awaitable_attrs.state_transitions, key=lambda x: x.id)
    if task_run.parameters_json is not None:
        task_run_dict['parameters_json'] = avoid_nans(task_run.parameters_json)
    if task_run.result_json is not None:
        task_run_dict['result_json'] = avoid_nans(task_run.result_json)
    task_run_dict['state_transitions'] = [
        get_json_dict(state_transition) for state_transition in sorted_state_transitions
    ]
    return task_run_dict
