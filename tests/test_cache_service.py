from app.services.cache import RetrievalCache


def test_retrieval_cache_stores_and_returns_copy():
    cache = RetrievalCache(max_entries=2)
    payload = [{"document": "foo"}]
    cache.set("hr", "question", payload)

    cached = cache.get("hr", "question")
    assert cached == payload
    assert cached is not payload  # ensure copy

    cached.append({"document": "bar"})
    cached_again = cache.get("hr", "question")
    assert len(cached_again) == 1
