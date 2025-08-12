import json
from datetime import datetime

import strawberry

from filament.db_models import TaskRun as TaskRunModel
from filament.redis_utils import r


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
    state_transitions: list['TaskRunStateTransition']
    child_tasks: list['TaskRun']
    task_type: 'TaskType'
    parameters_json: str | None
    result_json: str | None

    @strawberry.field
    async def logs(self) -> list['TaskRunLog']:
        result = []
        redis_key = f'filament_log:{self.task_type.func_address}:{self.task_uuid}'
        logs = await r.lrange(redis_key, 0, -1)
        for log in logs:
            result.append(TaskRunLog(**json.loads(log)))
        return result


@strawberry.type
class TaskRunStateTransition:
    id: int
    task_uuid: str
    from_state: str
    to_state: str
    state_since: datetime
    task_run: TaskRun


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

    @strawberry.field
    async def task_runs(self, info) -> list[TaskRun]:
        session = info.context['session']
        task_runs = (
            session.query(TaskRunModel)
            .where(TaskRunModel.task_type_id == self.id)
            .order_by(TaskRunModel.created_at.desc())
            .limit(99)
            .all()
        )
        return task_runs

    @strawberry.field
    async def latest_task_run(self, info) -> TaskRun | None:
        # task_runs = sorted(self.task_runs, key=lambda x: x.created_at, reverse=True)
        # return task_runs[0] if task_runs else None
        session = info.context['session']
        task_run = (
            session.query(TaskRunModel)
            .where(TaskRunModel.task_type_id == self.id)
            .order_by(TaskRunModel.state_since.desc())
            .limit(1)
            .first()
        )
        return task_run
