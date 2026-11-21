from arfigyelo_api.cache import TTLCache


class FakeClock:
    def __init__(self, start: float = 100.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def test_get_set_roundtrip():
    cache = TTLCache(10.0, clock=FakeClock())
    assert cache.get("missing") is None
    cache.set("k", "v")
    assert cache.get("k") == "v"


def test_expiry_after_ttl():
    clock = FakeClock()
    cache = TTLCache(10.0, clock=clock)
    cache.set("k", "v")
    clock.now += 9.9
    assert cache.get("k") == "v"
    clock.now += 0.2
    assert cache.get("k") is None


def test_ttl_none_never_expires():
    clock = FakeClock()
    cache = TTLCache(None, clock=clock)
    cache.set("k", "v")
    clock.now += 100_000.0
    assert cache.get("k") == "v"


def test_clear_removes_entries():
    cache = TTLCache(10.0, clock=FakeClock())
    cache.set("k", "v")
    cache.clear()
    assert cache.get("k") is None


def test_set_overwrites():
    cache = TTLCache(10.0, clock=FakeClock())
    cache.set("k", "first")
    cache.set("k", "second")
    assert cache.get("k") == "second"


def test_expired_entry_does_not_block_new_value():
    clock = FakeClock()
    cache = TTLCache(10.0, clock=clock)
    cache.set("k", "old")
    clock.now += 20.0
    assert cache.get("k") is None
    cache.set("k", "new")
    assert cache.get("k") == "new"
