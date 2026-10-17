import pytest


@pytest.fixture(autouse=True)
def no_intent_model_call(request, monkeypatch):
    """Unit tests never make the intent-fallback model call (integration tests may)."""
    if request.node.get_closest_marker("integration"):
        return

    async def refuse(question: str) -> str:
        raise RuntimeError("model calls are disabled in unit tests")

    monkeypatch.setattr("app.askflow.intent._ask_model", refuse)


@pytest.fixture(autouse=True)
def fresh_response_cache():
    """Endpoint responses are cached for two minutes; every test starts with an empty cache."""
    from app.brain import cache

    cache.clear_cache()
    yield
    cache.clear_cache()
