# project filament
# import asyncio
import hashlib
import inspect
import json
import logging
import pickle

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PydanticEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, BaseModel):
            return json.loads(obj.model_dump_json())
        elif issubclass(obj, BaseModel):
            return repr(obj)
        return super().default(obj)


def pydantic_json_dumps(obj, **kwargs):
    return json.dumps(obj, **kwargs, cls=PydanticEncoder)


def dict_cache_key(func, parameters):
    return dict(func=inspect.getsource(func), parameters=parameters)


def json_cache_key(func, parameters):
    return json.dumps(dict_cache_key(func, parameters), sort_keys=True, separators=(',', ':'))


def pickle_cache_key(func, parameters):
    return pickle.dumps(dict_cache_key(func, parameters))


def hash_cache_key(func, parameters):
    try:
        dict_cache_key_value = dict_cache_key(func, parameters)
        serialized_key = pydantic_json_dumps(dict_cache_key_value, separators=(',', ':'), sort_keys=True)
        serialized_key = serialized_key.encode('utf-8')
    except Exception as e:
        logger.exception(e)
        serialized_key = pickle_cache_key(func, parameters)
    return hashlib.md5(serialized_key).hexdigest()
