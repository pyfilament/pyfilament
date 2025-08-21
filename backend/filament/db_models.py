import logging
import os
import uuid
from contextlib import contextmanager
from datetime import datetime
from enum import Enum

from dotenv import load_dotenv
from pytz import timezone
from sqlalchemy import Index, String, null
from sqlalchemy.orm import declarative_base
from sqlmodel import TIMESTAMP, Column, Field, Relationship, Session, create_engine, text
from sqlmodel import SQLModel as BaseSQLModel

Base = declarative_base()


class SQLModel(BaseSQLModel, registry=Base.registry):
    pass


logger = logging.getLogger(__name__)

load_dotenv()
DATABASE_URL = os.getenv('FILAMENT_DB_URI', 'sqlite://filament.db')
engine = create_engine(DATABASE_URL)

REDIS_KEY_PREFIX = 'task_run:'


class TaskState(str, Enum):
    CREATED = 'created'
    RUNNING = 'running'
    CANCELLED = 'cancelled'
    FAILURE = 'failure'
    TIMEOUT = 'timeout'
    SUCCESS = 'success'
    RETRYING = 'retrying'
    CACHED = 'cached'


TaskState.TERMINAL = {TaskState.CANCELLED, TaskState.FAILURE, TaskState.SUCCESS, TaskState.CACHED}


def get_utc_now():
    return datetime.now().astimezone(timezone('UTC'))


class TaskRun(SQLModel, table=True):
    __tablename__ = 'task_run'

    id: int = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=get_utc_now, sa_column=Column(TIMESTAMP(timezone=True)))
    task_uuid: str = Field(
        default_factory=lambda: str(uuid.uuid4()), sa_column=Column(String, unique=True, nullable=False)
    )
    name: str | None = Field(default=None)
    state: str = Field(default=TaskState.CREATED, sa_column=Column(String, nullable=False))
    state_since: datetime = Field(default_factory=get_utc_now, sa_column=Column(TIMESTAMP(timezone=True)))
    heartbeat: datetime = Field(default_factory=get_utc_now, sa_column=Column(TIMESTAMP(timezone=True)))
    run_count: int = Field(default=0)
    parent_task_uuid: str | None = Field(default=None, foreign_key='task_run.task_uuid', index=True)

    parameters_json: str | None = Field(default=None)
    result_json: str | None = Field(default=None)

    state_transitions: list['TaskRunStateTransition'] = Relationship(back_populates='task_run')
    parent_task: 'TaskRun' = Relationship(
        back_populates='child_tasks', sa_relationship_kwargs={'remote_side': 'TaskRun.task_uuid'}
    )
    child_tasks: list['TaskRun'] = Relationship(back_populates='parent_task')
    task_type_id: int = Field(default=None, foreign_key='task_type.id', index=True)
    task_type: 'TaskType' = Relationship(back_populates='task_runs')

    def __repr__(self):
        return f'TaskRun(task_uuid={self.task_uuid[-8:]}, name={self.name}, state={self.state}, state_since={self.state_since}, heartbeat={self.heartbeat}, run_count={self.run_count})'

    def __str__(self):
        return self.__repr__()

    __table__args = (
        Index('idx_task_run_state', state.sa_column),
        Index('idx_task_run_created_at', created_at.sa_column),
        Index('idx_task_run_state_since', state_since.sa_column),
    )


class TaskType(SQLModel, table=True):
    __tablename__ = 'task_type'

    id: int = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=get_utc_now, sa_column=Column(TIMESTAMP(timezone=True)))
    name: str = Field(default=None)
    func_address: str = Field(default=None, unique=True)

    task_runs: list[TaskRun] = Relationship(back_populates='task_type')


class TaskRunStateTransition(SQLModel, table=True):
    __tablename__ = 'task_run_state_transition'

    id: int = Field(default=None, primary_key=True)
    task_uuid: str = Field(default_factory=lambda: str(uuid.uuid4()), foreign_key='task_run.task_uuid', index=True)
    from_state: str
    to_state: str
    state_since: datetime = Field(default_factory=get_utc_now, sa_column=Column(TIMESTAMP(timezone=True)))
    task_run: 'TaskRun' = Relationship(back_populates='state_transitions')


# SQLModel.metadata.create_all(engine)


def get_session(autoflush=True):
    return Session(engine, autoflush=autoflush)


@contextmanager
def session_scope(commit=True, autoflush=True):
    session = get_session(autoflush=autoflush)
    try:
        yield session
        if commit:
            session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()
