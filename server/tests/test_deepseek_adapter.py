"""DeepSeek adapter connection-policy tests."""

from novelwb.adapters.llm import deepseek


def test_deepseek_client_ignores_environment_proxies(monkeypatch):
    captured: dict = {}

    class DummyClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def close(self):
            return None

    monkeypatch.setattr(deepseek.httpx, "Client", DummyClient)

    adapter = deepseek.DeepSeekAdapter(api_key="test-key")

    assert captured["base_url"] == "https://api.deepseek.com"
    assert captured["trust_env"] is False
    adapter.close()


def test_graph2_uses_long_timeout_and_bounded_transport_retry(monkeypatch):
    adapter = deepseek.DeepSeekAdapter(api_key="test-key")
    captured: dict = {}

    def fake_call_with_retry(rendered_prompt, **kwargs):
        captured.update(kwargs)
        return '{"ok": true}', 10, 3, 12

    monkeypatch.setattr(adapter, "_call_with_retry", fake_call_with_retry)
    response = adapter.call(
        "prompt",
        step_id="step_1",
        prompt_key="graph2.storyField",
        prompt_version="1.0",
        prompt_hash="hash",
    )

    assert response.text == '{"ok": true}'
    assert captured["timeout"] == 300.0
    assert captured["max_retries"] == 1
    adapter.close()


def test_graph4_planning_and_prose_use_independent_timeouts(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_GRAPH4_PLAN_TIMEOUT", raising=False)
    monkeypatch.delenv("DEEPSEEK_BLOCKS_TIMEOUT", raising=False)
    adapter = deepseek.DeepSeekAdapter(api_key="test-key")
    calls: list[dict] = []

    def fake_call_with_retry(rendered_prompt, **kwargs):
        calls.append(kwargs)
        return '{"ok": true}', 10, 3, 12

    monkeypatch.setattr(adapter, "_call_with_retry", fake_call_with_retry)
    for prompt_key in ("graph4.eventPlan", "graph4.blocksWrite"):
        adapter.call(
            "prompt",
            step_id=f"step_{prompt_key}",
            prompt_key=prompt_key,
            prompt_version="1.0",
            prompt_hash="hash",
        )

    assert calls[0]["timeout"] == 300.0
    assert calls[0]["max_retries"] == 1
    assert calls[1]["timeout"] == 180.0
    assert calls[1]["max_retries"] == 1
    adapter.close()


def test_graph_e_uses_one_long_request_without_transport_retry(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_GRAPHE_TIMEOUT", raising=False)
    monkeypatch.delenv("DEEPSEEK_GRAPHE_RETRIES", raising=False)
    adapter = deepseek.DeepSeekAdapter(api_key="test-key")
    captured: dict = {}

    def fake_call_with_retry(rendered_prompt, **kwargs):
        captured.update(kwargs)
        return '{"ok": true}', 10, 3, 12

    monkeypatch.setattr(adapter, "_call_with_retry", fake_call_with_retry)
    adapter.call(
        "prompt",
        step_id="step_graph_e",
        prompt_key="graphE.extract",
        prompt_version="1.0",
        prompt_hash="hash",
    )

    assert captured["timeout"] == 180.0
    assert captured["max_retries"] == 0
    adapter.close()
