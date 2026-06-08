from beartype.typing import Callable
from pydantic import BaseModel, Field


class FuncRegistryEntry(BaseModel):
    func: Callable
    class_: type | None = None

    @property
    def func_address(self) -> str:
        return get_func_address(self.func)

    @property
    def class_address(self) -> str | None:
        qualname = self.func.__qualname__
        if '.' in qualname:
            parts = qualname.split('.')
            if len(parts) == 2:
                class_name = parts[0]
                return f'{self.func.__module__}:{class_name}'
        return None


class FuncRegistry(BaseModel):
    entries: dict[str, FuncRegistryEntry] = Field(default_factory=dict)

    def register(self, func: Callable, class_: type | None = None) -> FuncRegistryEntry:
        func_address = get_func_address(func)
        if func_address in self.entries:
            entry = self.entries[func_address]
            if func is not None and func != entry.func:
                entry.func = func
            if class_ is not None and class_ != entry.class_:
                entry.class_ = class_
        else:
            entry = FuncRegistryEntry(func=func, class_=class_)
            self.entries[func_address] = entry
        return entry

    def lookup(self, func_address: str) -> FuncRegistryEntry:
        if func_address in self.entries:
            return self.entries[func_address]
        raise KeyError(f'FuncRegistryEntry with func_address {func_address} not found')


_FUNC_REGISTRY = FuncRegistry()


def lookup_func_entry(func_address: str) -> FuncRegistryEntry:
    return _FUNC_REGISTRY.lookup(func_address)


def register_func(func: Callable, class_: type | None = None) -> FuncRegistryEntry:
    return _FUNC_REGISTRY.register(func, class_)


def get_func_address(func: Callable) -> str:
    return f'{func.__module__}:{func.__qualname__}'


def get_registered_entries() -> list[FuncRegistryEntry]:
    return list(_FUNC_REGISTRY.entries.values())
