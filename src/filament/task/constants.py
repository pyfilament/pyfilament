from enum import Enum

DEFAULT_HEARTBEAT_INTERVAL = 60
DEFAULT_MONITOR_INTERVAL = 10


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
