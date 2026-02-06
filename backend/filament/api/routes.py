import json
import logging

from fastapi import Request, Response
from werkzeug.exceptions import NotFound

from filament.api.app import app
from filament.api.logic.task_run_dict import deep_get_task_run_dict
from filament.db_models import TaskRun as TaskRunModel
from filament.db_session import session_scope
from filament.utils import rename_keys_to_camel_case

logger = logging.getLogger(__name__)


@app.get('/tasks')
async def root():
    return {'message': 'Hello World'}


@app.get('/api/task-run/{task_run_id}')
async def get_task_run(request: Request, task_run_id: int, max_child_tasks: int = 100, child_depth: int = 3):
    with session_scope() as session:
        task_run = session.get(TaskRunModel, task_run_id)
        if task_run is None:
            raise NotFound(f'TaskRun with ID {task_run_id} not found')
        task_run_dict = deep_get_task_run_dict(task_run, max_child_tasks, child_depth)

    return rename_keys_to_camel_case(task_run_dict)


@app.get('/api/task-runs/{task_run_ids_str}')
async def get_task_runs(request: Request, task_run_ids_str: str, max_child_tasks: int = 100, child_depth: int = 3):
    task_run_ids = [int(id) for id in task_run_ids_str.split(',')]
    with session_scope() as session:
        task_runs = []
        for task_run_id in task_run_ids:
            task_run = session.get(TaskRunModel, task_run_id)
            if task_run is None:
                raise NotFound(f'TaskRun with ID {task_run_id} not found')
            task_runs.append(deep_get_task_run_dict(task_run, max_child_tasks, child_depth))
        return rename_keys_to_camel_case(task_runs)


@app.get('/api/task-run/{task_run_id}/download')
async def download_task_run(request: Request, task_run_id: int, max_child_tasks: int = 100, child_depth: int = 3):
    with session_scope() as session:
        task_run = session.get(TaskRunModel, task_run_id)
        if task_run is None:
            raise NotFound(f'TaskRun with ID {task_run_id} not found')
        task_run_dict = deep_get_task_run_dict(task_run, max_child_tasks, child_depth)

    file_content = json.dumps(rename_keys_to_camel_case(task_run_dict), indent=2).encode('utf-8')
    filename = f'task_run_{task_run_id}.json'
    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return Response(
        content=file_content,
        media_type='application/json',
        headers=headers,
    )
