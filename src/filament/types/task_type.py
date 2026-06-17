import inspect
import logging
import types

from filament.types.base import FilamentBaseModel
from filament.types.task_config import FilamentTaskConfig
from filament.types.task_run import FilamentTaskRun
from pydantic import Field, PrivateAttr

from filament.logic.events import EventManager
from filament.logic.func_registry import lookup_func_entry, register_func


class FilamentTaskType(FilamentBaseModel):
    func_address: str
    name: str
    _func: callable = PrivateAttr()
    config: FilamentTaskConfig = Field(default_factory=lambda: FilamentTaskConfig())
    _events: EventManager = PrivateAttr()

    def __init__(
        self,
        _func=None,
        func_address=None,
        name=None,
        events: EventManager | None = None,
        **config_kwargs,
    ):
        if _func is not None:
            func_address = register_func(_func).func_address
        else:
            assert func_address is not None, 'func_address must be provided if func is not'
            _func = lookup_func_entry(func_address).func
        assert inspect.iscoroutinefunction(_func) or inspect.isasyncgenfunction(_func), f'Unsupported function: {_func}'
        if name is None:
            name = func_address
        config = FilamentTaskConfig(**config_kwargs)
        if events is None:
            events = EventManager()
        super().__init__(
            func_address=func_address,
            name=name,
            config=config,
        )
        self._events = events
        self._func = _func
        self._logger = logging.getLogger(func_address)

    def model_post_init(self, __context):
        func_entry = lookup_func_entry(self.func_address)
        self._func = func_entry.func

    def __call__(self, *task_args, **task_kwargs) -> FilamentTaskRun:
        return FilamentTaskRun(
            type=self,
            task_args=task_args,
            task_kwargs=task_kwargs,
            config=self.config,
            events=self._events,
        )

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return types.MethodType(self, instance)
