from beartype import beartype

from filament.logic.events import EventManager
from filament.state.task_run_state import initialize_task_run_state, set_heartbeat, set_task_result, transition_state


@beartype
def register_task_events(events: EventManager) -> None:
    events.on('task_run.request')(initialize_task_run_state)
    events.on('task_run.before_call')(initialize_task_run_state)
    events.on('task_run.after_call')(set_task_result)
    events.on('task_run.state_transition')(transition_state)
    events.on('task_run.heartbeat')(set_heartbeat)
