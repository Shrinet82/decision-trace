import pytest


@pytest.fixture(autouse=True)
def no_intent_model_call(request, monkeypatch):
    """Unit tests never make the intent-fallback model call (integration tests may)."""
    if request.node.get_closest_marker("integration"):
        return

    async def refuse(question: str) -> str:
        raise RuntimeError("model calls are disabled in unit tests")

    monkeypatch.setattr("app.askflow.intent._ask_model", refuse)
