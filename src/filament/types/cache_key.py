from filament.types.base import FilamentBaseModel
from pydantic import PrivateAttr

from filament.logic.module_type_registry import lookup_module_type, register_module_type


class FilamentCacheKey(FilamentBaseModel):
    func_address: str
    _func: callable = PrivateAttr()

    def __init__(self, func=None, **kwargs):
        if func is not None:
            kwargs['func_address'] = register_module_type(func)
        super().__init__(**kwargs)

    def model_post_init(self, __context):
        self._func = lookup_module_type(self.func_address)
