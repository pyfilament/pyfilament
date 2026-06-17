from filament.types.base import FilamentBaseModel
from pydantic import PrivateAttr

from filament.logic.module_type_registry import lookup_module_type, register_module_type


class FilamentExceptionType(FilamentBaseModel):
    exc_type_address: str
    _exc_type: type = PrivateAttr()

    def __init__(self, exc_type=None, **kwargs):
        if exc_type is not None:
            kwargs['exc_type_address'] = register_module_type(exc_type)
        super().__init__(**kwargs)

    def model_post_init(self, __context):
        self._exc_type = lookup_module_type(self.exc_type_address)
