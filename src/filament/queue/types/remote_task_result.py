import json
import traceback
from typing import TYPE_CHECKING

from filament.types.base import FilamentBaseModel
from pydantic import Field, PrivateAttr

from filament.logic.module_type_registry import lookup_module_type, register_module_type
from filament.logic.utils import get_json_encodable
from filament.queue.types.remote_exception import FilamentRemoteException

if TYPE_CHECKING:
    from filament.queue.types.remote_task_type import FilamentRemoteTaskType


class FilamentRemoteTaskResult(FilamentBaseModel):
    type: FilamentRemoteTaskType
    task_uuid: str
    result_json: str | None = Field(default=None)
    exception_json: str | None = Field(default=None)
    _result: any = PrivateAttr(default=None)
    _exception: Exception | None = PrivateAttr(default=None)

    def __init__(self, result=None, exception=None, **kwargs):
        if result is not None:
            kwargs['result_json'] = json.dumps(get_json_encodable(result))
        if exception is not None:
            kwargs['exception_json'] = json.dumps(
                {
                    'type_address': register_module_type(type(exception)),
                    'message': str(exception),
                    # "args": base64.b64encode(pickle.dumps(exception.args)).decode(),
                    'traceback': traceback.format_exc(),
                }
            )
        super().__init__(**kwargs)

    def model_post_init(self, __context):
        if self.result_json is not None:
            self._result = json.loads(self.result_json)
        if self.exception_json is not None:
            exception_dict = json.loads(self.exception_json)
            exc_type = lookup_module_type(exception_dict['type_address'])
            message = exception_dict['message']
            traceback = exception_dict['traceback']
            # self._exception = exc_type(message)
            self._exception = FilamentRemoteException(exc_type=exc_type, message=message, traceback=traceback)
            # args = pickle.loads(base64.b64decode(exception_dict["args"]))
            # self._exception = exc_type(*args)
