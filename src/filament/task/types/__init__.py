import sys
from .base import FilamentBaseModel
from .task_config import FilamentTaskConfig
from .task_run import FilamentTaskRun
from .task_result import FilamentTaskResult
from .task_type import FilamentTaskType
from .remote_task_run import FilamentRemoteTaskRun
from .exception_type import FilamentExceptionType
from .cache_key import FilamentCacheKey
from .remote_exception import FilamentRemoteException


MODELS = [
    FilamentBaseModel,
    FilamentTaskConfig,
    FilamentTaskRun,
    FilamentTaskResult,
    FilamentTaskType,
    FilamentRemoteTaskRun,
    FilamentExceptionType,
    FilamentCacheKey,
    FilamentRemoteException,
]

__all__ = [model.__name__ for model in MODELS]

# resolve circular imports for pydantic and beartype


def _export_models():
    for to_model in MODELS:
        to_module = sys.modules[to_model.__module__]
        for from_model in MODELS:
            if from_model is not to_model:
                setattr(to_module, from_model.__name__, from_model)


def _rebuild_models():
    for model in FilamentBaseModel.__subclasses__():
        model.model_rebuild()


_export_models()
_rebuild_models()
