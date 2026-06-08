import json
from datetime import datetime

import strawberry
from strawberry import Info
from sqlalchemy import select

from filament.db_models import TaskRun as TaskRunModel
from filament.redis_utils import r


async def get_logs(
    task_run: TaskRunModel, with_children: bool = True, max_depth: int = 3, max_num_children: int = 100
) -> list[dict]:
    logs = []
    redis_key = f'filament_log:{(await task_run.awaitable_attrs.task_type).func_address}:{task_run.task_uuid}'
    range_results = await r.lrange(redis_key, 0, -1)
    for range_result in range_results:
        logs.append(json.loads(range_result))
    if with_children and max_depth > 0:
        for child_task in (await task_run.awaitable_attrs.child_tasks)[:max_num_children]:
            logs.extend(await get_logs(child_task, with_children, max_depth - 1, max_num_children))
    return sorted(logs, key=lambda x: x['timestamp'])


@strawberry.type
class TaskRun:
    id: int
    task_uuid: str
    name: str | None
    created_at: datetime
    state: str
    state_since: datetime
    heartbeat: datetime
    run_count: int
    parent_task_uuid: str | None
    parameters_json: str | None
    result_json: str | None

    @strawberry.field
    async def task_type(self) -> 'TaskType':
        return await self.awaitable_attrs.task_type

    @strawberry.field
    async def state_transitions(self) -> list['TaskRunStateTransition']:
        return await self.awaitable_attrs.state_transitions

    @strawberry.field
    async def child_tasks(self) -> list['TaskRun']:
        return await self.awaitable_attrs.child_tasks

    @strawberry.field
    async def logs(
        self, with_children: bool = True, max_depth: int = 3, max_num_children: int = 100
    ) -> list['TaskRunLog']:
        logs = await get_logs(self, with_children, max_depth, max_num_children)
        return [TaskRunLog(**log) for log in logs]

    @strawberry.field
    async def task_runs_stack(self) -> list['TaskRun']:
        current = self
        task_runs_stack = []
        task_runs_stack.append(current)
        while await current.awaitable_attrs.parent_task:
            task_runs_stack.append(await current.awaitable_attrs.parent_task)
            current = await current.awaitable_attrs.parent_task
        return list(reversed(task_runs_stack))


@strawberry.type
class TaskRunStateTransition:
    id: int
    task_uuid: str
    from_state: str
    to_state: str
    state_since: datetime

    @strawberry.field
    async def task_run(self) -> TaskRun:
        return await self.awaitable_attrs.task_run


@strawberry.type
class TaskRunLog:
    timestamp: float
    level: str
    name: str
    message: str


@strawberry.type
class TaskType:
    id: int
    func_address: str
    name: str | None
    parameters_spec: str | None
    result_spec: str | None

    @strawberry.field
    async def task_runs(self, info: Info) -> list[TaskRun]:
        session = info.context['session']
        statement = (
            select(TaskRunModel)
            .where(TaskRunModel.task_type_id == self.id)
            .order_by(TaskRunModel.created_at.desc())
            .limit(99)
        )
        task_runs = (await session.execute(statement)).scalars().all()
        return task_runs

    @strawberry.field
    async def latest_task_run(self, info: Info) -> TaskRun | None:
        session = info.context['session']
        statement = (
            select(TaskRunModel)
            .where(TaskRunModel.task_type_id == self.id)
            .order_by(TaskRunModel.state_since.desc())
            .limit(1)
        )
        task_run = (await session.execute(statement)).scalars().one_or_none()
        return task_run
