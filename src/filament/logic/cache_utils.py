import base64
import pickle

from filament.redis.client import r

CACHE_KEY_PREFIX = 'cache:'

DEFAULT_TTL = 60 * 60 * 24


def get_key(key):
    return f'{CACHE_KEY_PREFIX}{key}'


async def cache_has_key(key):
    return await r.exists(get_key(key))


async def cache_get(key):
    base64_encoded_value = await r.get(get_key(key))
    if base64_encoded_value is None:
        return None
    pickled_value = base64.b64decode(base64_encoded_value)
    return pickle.loads(pickled_value)


async def cache_set(key, value, ttl=None):
    if ttl is None:
        ttl = DEFAULT_TTL
    pickled_value = pickle.dumps(value)
    base64_encoded_value = base64.b64encode(pickled_value).decode('utf-8')
    await r.set(get_key(key), base64_encoded_value, ex=ttl)
