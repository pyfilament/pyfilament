import uuid
from datetime import datetime, timezone

from filament.constants import TaskState
from sqlalchemy import Column, ForeignKey, Index, Integer, String
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import TIMESTAMP

Base = declarative_base()


def get_uuid():
    return str(uuid.uuid4())


def get_utc_now():
    return datetime.now().astimezone(timezone.utc)


class TaskRun(AsyncAttrs, Base):
    __tablename__ = 'task_run'

    id = Column(Integer, primary_key=True)
    created_at = Column(TIMESTAMP(timezone=True), default=get_utc_now)
    task_uuid = Column(String, unique=True, nullable=False, default=get_uuid)
    name = Column(String, nullable=True)
    state = Column(String, nullable=False, default=TaskState.CREATED)
    state_since = Column(TIMESTAMP(timezone=True), default=get_utc_now)
    heartbeat = Column(TIMESTAMP(timezone=True), default=get_utc_now)
    run_count = Column(Integer, default=0, nullable=False)
    parent_task_uuid = Column(String, ForeignKey('task_run.task_uuid'), nullable=True, index=True)
    parameters_json = Column(String, nullable=True)
    result_json = Column(String, nullable=True)
    task_type_id = Column(Integer, ForeignKey('task_type.id'), index=True, nullable=False)

    state_transitions = relationship('TaskRunStateTransition', back_populates='task_run', uselist=True)
    parent_task = relationship('TaskRun', back_populates='child_tasks', remote_side='TaskRun.task_uuid', uselist=False)
    child_tasks = relationship('TaskRun', back_populates='parent_task', uselist=True)
    task_type = relationship('TaskType', back_populates='task_runs', uselist=False)

    def __repr__(self):
        return f'TaskRun(task_uuid={self.task_uuid[-8:]}, name={self.name}, state={self.state}, state_since={self.state_since}, heartbeat={self.heartbeat}, run_count={self.run_count})'

    def __str__(self):
        return self.__repr__()

    __table_args__ = (
        Index('idx_task_run_state', state),
        Index('idx_task_run_created_at', created_at),
        Index('idx_task_run_state_since', state_since),
        Index('idx_task_run_id_task_type_id_created_at', id, task_type_id, created_at),
        Index('idx_task_run_id_task_type_id_created_at_desc', id, task_type_id, created_at.desc()),
        Index('idx_task_run_type_created_at_desc', task_type_id, created_at.desc()),
        Index('idx_task_run_type_state_since_desc', task_type_id, state_since.desc()),
    )


class TaskType(Base):
    __tablename__ = 'task_type'

    id = Column(Integer, primary_key=True)
    created_at = Column(TIMESTAMP(timezone=True), default=get_utc_now)
    name = Column(String, nullable=False)
    func_address = Column(String, unique=True, nullable=False)
    parameters_spec = Column(String, nullable=True)
    result_spec = Column(String, nullable=True)

    task_runs = relationship('TaskRun', back_populates='task_type', uselist=True)


class TaskRunStateTransition(Base):
    __tablename__ = 'task_run_state_transition'

    id = Column(Integer, primary_key=True)
    task_uuid = Column(String, ForeignKey('task_run.task_uuid'), index=True, default=get_uuid, nullable=False)
    from_state = Column(String, nullable=False)
    to_state = Column(String, nullable=False)
    state_since = Column(TIMESTAMP(timezone=True), default=get_utc_now)

    task_run = relationship('TaskRun', back_populates='state_transitions', uselist=False)
