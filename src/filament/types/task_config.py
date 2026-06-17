from filament.constants import DEFAULT_HEARTBEAT_INTERVAL, DEFAULT_MONITOR_INTERVAL
from filament.types.base import FilamentBaseModel
from filament.types.cache_key import FilamentCacheKey
from filament.types.exception_type import FilamentExceptionType
from pydantic import Field

from filament.logic.cache_keys import hash_cache_key


class FilamentTaskConfig(FilamentBaseModel):
    timeout: float | None = Field(default=None)
    start_immediately: bool = Field(default=False)
    propagate: bool = Field(default=True)
    tries: int = Field(default=1)
    delay: float = Field(default=0)
    backoff_base: float = Field(default=2)
    retry_exceptions: list[FilamentExceptionType] = Field(default=[FilamentExceptionType(Exception)])
    no_retry_exceptions: list[FilamentExceptionType] = Field(default=[])
    cache: bool = Field(default=False)
    cache_key: FilamentCacheKey = Field(default=FilamentCacheKey(hash_cache_key))
    cache_ttl: int | None = Field(default=None)
    refresh_cache: bool = Field(default=False)
    heartbeat: bool = Field(default=True)
    heartbeat_interval: float | None = Field(default=DEFAULT_HEARTBEAT_INTERVAL)
    monitor: bool = Field(default=True)
    monitor_interval: float | None = Field(default=DEFAULT_MONITOR_INTERVAL)
    max_concurrent: int | None = Field(default=None)
    rate_limit: float | None = Field(default=None)
    is_redact_input: bool = Field(default=False)
    is_redact_output: bool = Field(default=False)

    def __init__(self, **kwargs):
        if 'retry_exceptions' in kwargs:
            kwargs['retry_exceptions'] = self._get_retry_exc_types(kwargs['retry_exceptions'])
        if 'no_retry_exceptions' in kwargs:
            kwargs['no_retry_exceptions'] = self._get_retry_exc_types(kwargs['no_retry_exceptions'])
        if 'cache_key' in kwargs:
            kwargs['cache_key'] = (
                FilamentCacheKey(kwargs['cache_key']) if callable(kwargs['cache_key']) else kwargs['cache_key']
            )
        super().__init__(**kwargs)

    def _get_retry_exc_types(
        self, exception_types: list[type[Exception] | dict | FilamentExceptionType]
    ) -> list[FilamentExceptionType]:
        exception_types = []
        for exc_type in exception_types:
            if isinstance(exc_type, type) and issubclass(exc_type, Exception):
                exception_types.append(FilamentExceptionType(exc_type))
            elif isinstance(exc_type, dict):
                exception_types.append(FilamentExceptionType(**exc_type))
            else:
                exception_types.append(exc_type)
        return exception_types
