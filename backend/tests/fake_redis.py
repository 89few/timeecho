from __future__ import annotations

import fnmatch
import random
import time
from collections import defaultdict


class FakeAsyncRedis:
    def __init__(self, decode_responses: bool = True):
        self.decode_responses = decode_responses
        self.store: dict[str, str] = {}
        self.expires: dict[str, float] = {}
        self.sets: dict[str, set[str]] = defaultdict(set)
        self.zsets: dict[str, dict[str, float]] = defaultdict(dict)
        self.lists: dict[str, list[str]] = defaultdict(list)

    def _expired(self, key: str) -> bool:
        exp = self.expires.get(key)
        if exp is not None and exp <= time.time():
            self.store.pop(key, None)
            self.sets.pop(key, None)
            self.zsets.pop(key, None)
            self.lists.pop(key, None)
            self.expires.pop(key, None)
            return True
        return False

    async def get(self, key: str):
        if self._expired(key):
            return None
        return self.store.get(key)

    async def set(
        self,
        key: str,
        value,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
    ):
        if nx and await self.exists(key):
            return False
        self.store[key] = str(value)
        if ex:
            self.expires[key] = time.time() + ex
        elif px:
            self.expires[key] = time.time() + (px / 1000)
        return True

    async def eval(self, script: str, numkeys: int, *values):
        key, expected = str(values[0]), str(values[1])
        if await self.get(key) == expected:
            return await self.delete(key)
        return 0


    async def keys(self, pattern: str):
        all_keys = set(self.store) | set(self.sets) | set(self.zsets) | set(self.lists)
        return [k for k in all_keys if not self._expired(k) and fnmatch.fnmatch(k, pattern)]

    async def exists(self, key: str):
        if self._expired(key):
            return 0
        return int(key in self.store or key in self.sets or key in self.zsets or key in self.lists)

    async def delete(self, *keys: str):
        count = 0
        for key in keys:
            existed = key in self.store or key in self.sets or key in self.zsets or key in self.lists
            self.store.pop(key, None)
            self.sets.pop(key, None)
            self.zsets.pop(key, None)
            self.lists.pop(key, None)
            self.expires.pop(key, None)
            count += int(existed)
        return count

    async def incr(self, key: str):
        if self._expired(key):
            self.store.pop(key, None)
        value = int(self.store.get(key, 0)) + 1
        self.store[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int):
        self.expires[key] = time.time() + seconds
        return True

    async def flushall(self):
        self.store.clear(); self.expires.clear(); self.sets.clear(); self.zsets.clear(); self.lists.clear()
        return True

    async def aclose(self):
        return None

    async def ping(self):
        return True

    async def zadd(self, key: str, mapping: dict[str, float]):
        self.zsets[key].update({str(k): float(v) for k, v in mapping.items()})
        return len(mapping)

    async def zrangebyscore(self, key: str, min=0, max=0, start: int | None = None, num: int | None = None):
        if self._expired(key):
            return []
        lo = float(min)
        hi = float(max)
        items = [m for m, score in sorted(self.zsets.get(key, {}).items(), key=lambda x: x[1]) if lo <= score <= hi]
        if start is not None and num is not None:
            items = items[start:start + num]
        return items

    async def zrem(self, key: str, *members):
        count = 0
        for m in members:
            if str(m) in self.zsets.get(key, {}):
                self.zsets[key].pop(str(m), None)
                count += 1
        return count

    async def sadd(self, key: str, *members):
        before = len(self.sets[key])
        for m in members:
            self.sets[key].add(str(m))
        return len(self.sets[key]) - before

    async def srem(self, key: str, *members):
        count = 0
        for m in members:
            if str(m) in self.sets.get(key, set()):
                self.sets[key].remove(str(m)); count += 1
        return count

    async def srandmember(self, key: str):
        if self._expired(key):
            return None
        values = list(self.sets.get(key, set()))
        return random.choice(values) if values else None

    async def sismember(self, key: str, member):
        return str(member) in self.sets.get(key, set())

    async def rpush(self, key: str, *values):
        self.lists[key].extend(str(v) for v in values)
        return len(self.lists[key])

    async def lrange(self, key: str, start: int, end: int):
        values = self.lists.get(key, [])
        if end == -1:
            end = len(values) - 1
        return values[start:end + 1]
