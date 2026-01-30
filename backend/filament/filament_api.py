from filament.setup_logging import setup_logging

"""import logging first"""

import json
import logging

import strawberry
from fastapi import Depends, FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from strawberry.extensions import SchemaExtension
from strawberry.fastapi import GraphQLRouter
from werkzeug.exceptions import NotFound

import filament.resolvers.task as task_resolver
from filament.db_models import Base
from filament.db_models import TaskRun as TaskRunModel
from filament.db_session import session_scope
from filament.types.task import TaskRun, TaskType
from filament.utils import avoid_nans, get_json_dict, rename_keys_to_camel_case

logger = logging.getLogger(__name__)

app = FastAPI()


def get_session_from_request(request: Request):
    return request.state.session


async def get_context(
    session=Depends(get_session_from_request),
):
    return {
        'session': session,
    }


class SessionFlusher(SchemaExtension):
    def resolve(self, _next, root, info, *args, **kwargs):
        if (
            info.path is not None
            and info.path.key is not None
            and (info.path.key == 'id' or info.path.key.endswith('_id'))
        ):
            if isinstance(root, Base) and getattr(root, info.path.key, None) is None:
                if info.context is not None and 'session' in info.context:
                    info.context['session'].flush()
        return _next(root, info, *args, **kwargs)


@strawberry.type
class Query:
    get_task_run: TaskRun = strawberry.field(resolver=task_resolver.get_task_run)
    get_task_type: TaskType = strawberry.field(resolver=task_resolver.get_task_type)
    get_task_types: list[TaskType] = strawberry.field(resolver=task_resolver.get_task_types)
    get_task_runs: list[TaskRun] = strawberry.field(resolver=task_resolver.get_task_runs)
    get_task_runs_by_ids: list[TaskRun] = strawberry.field(resolver=task_resolver.get_task_runs_by_ids)
    get_task_types_by_ids: list[TaskType] = strawberry.field(resolver=task_resolver.get_task_types_by_ids)
    get_task_type_stack_runs: list[TaskRun] = strawberry.field(resolver=task_resolver.get_task_type_stack_runs)


@strawberry.type
class Mutation:
    cancel_task_run: TaskRun = strawberry.field(resolver=task_resolver.cancel_task_run)
    run_task: TaskRun = strawberry.field(resolver=task_resolver.run_task)


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[SessionFlusher],
)


@app.get('/tasks')
async def root():
    return {'message': 'Hello World'}


@app.get('/api/task-run/{task_run_id}')
async def get_task_run(request: Request, task_run_id: int, max_child_tasks: int = 100):
    with session_scope() as session:
        task_run = session.get(TaskRunModel, task_run_id)
        if task_run is None:
            raise NotFound(f'TaskRun with ID {task_run_id} not found')
        task_run_dict = get_task_run_dict(task_run, max_child_tasks)

    return rename_keys_to_camel_case(task_run_dict)


@app.get('/api/task-runs/{task_run_ids_str}')
async def get_task_runs(request: Request, task_run_ids_str: str, max_child_tasks: int = 100):
    task_run_ids = [int(id) for id in task_run_ids_str.split(',')]
    with session_scope() as session:
        task_runs = []
        for task_run_id in task_run_ids:
            task_run = session.get(TaskRunModel, task_run_id)
            if task_run is None:
                raise NotFound(f'TaskRun with ID {task_run_id} not found')
            task_runs.append(get_task_run_dict(task_run, max_child_tasks))
        return rename_keys_to_camel_case(task_runs)


@app.get('/api/task-run/{task_run_id}/download')
async def download_task_run(request: Request, task_run_id: int, max_child_tasks: int = 100):
    with session_scope() as session:
        task_run = session.get(TaskRunModel, task_run_id)
        if task_run is None:
            raise NotFound(f'TaskRun with ID {task_run_id} not found')
        task_run_dict = get_task_run_dict(task_run, max_child_tasks)

    file_content = json.dumps(rename_keys_to_camel_case(task_run_dict), indent=2).encode('utf-8')
    filename = f'task_run_{task_run_id}.json'
    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return Response(
        content=file_content,
        media_type='application/json',
        headers=headers,
    )


def get_task_run_dict(task_run: TaskRunModel, max_child_tasks: int = 100) -> dict:
    task_run_dict = get_json_dict(task_run)
    task_run_dict['task_type'] = get_json_dict(task_run.task_type)
    sorted_child_tasks = sorted(task_run.child_tasks, key=lambda x: x.id)
    task_run_dict['child_tasks'] = [
        get_task_run_dict(child_task_run, max_child_tasks) for child_task_run in sorted_child_tasks[:max_child_tasks]
    ]
    sorted_state_transitions = sorted(task_run.state_transitions, key=lambda x: x.id)
    if task_run.parameters_json is not None:
        task_run_dict['parameters_json'] = avoid_nans(task_run.parameters_json)
    if task_run.result_json is not None:
        task_run_dict['result_json'] = avoid_nans(task_run.result_json)
    task_run_dict['state_transitions'] = [
        get_json_dict(state_transition) for state_transition in sorted_state_transitions
    ]
    return task_run_dict


class SessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        with session_scope() as session:
            request.state.session = session
            return await call_next(request)


app.add_middleware(SessionMiddleware)
graphql_app = GraphQLRouter(
    schema,
    context_getter=get_context,
)
app.include_router(graphql_app, prefix='/graphql')
