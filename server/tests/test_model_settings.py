"""Model settings lifecycle, secret boundaries and protocol integration without network."""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from novelwb.adapters.llm import configured
from novelwb.adapters.llm.configured import ConfiguredAdapter, ModelConnectionError
from novelwb.api import deps
from novelwb.api.main import app
from novelwb.api.routers import projects
from novelwb.core.model_settings import ProfileInput, ResolvedProfile
from novelwb.storage import model_settings_store
from novelwb.storage.model_settings_store import ModelSettingsStore, SettingsConflict

SECRET = "test-only-model-key"
BASE = "/settings/models"


def body(**overrides):
    return {
        "name": "测试模型",
        "protocol": "openai",
        "model": "test-model",
        "base_url": "https://models.example.invalid/proxy/v1",
        "revision": 0,
        **overrides,
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(deps, "WORKSPACE_ROOT", workspace)
    monkeypatch.setattr(projects, "WORKSPACE_ROOT", workspace)
    monkeypatch.setenv("NOVELWB_LLM_ADAPTER", "mock")
    monkeypatch.delenv("NOVELWB_MODEL_SETTINGS_DISABLED", raising=False)
    deps._build_orchestrator.cache_clear()
    with TestClient(
        app,
        base_url="http://127.0.0.1:8000",
        client=("127.0.0.1", 43210),
        headers={"X-Model-Settings": "1"},
    ) as test_client:
        yield test_client
    deps._build_orchestrator.cache_clear()


def saved(client, **overrides):
    response = client.post(BASE + "/profiles", json=body(**overrides))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def install_transport(monkeypatch, handler):
    real_client = httpx.Client
    captured = []

    def factory(**kwargs):
        captured.append(kwargs)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(configured.httpx, "Client", factory)
    return captured


def completion(text="OK"):
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3},
    }


def test_empty_settings_read_does_not_create_workspace(client):
    response = client.get(BASE)
    assert response.json()["data"]["profiles"] == []
    assert not deps.WORKSPACE_ROOT.exists()


def test_save_edit_restart_switch_and_delete_keep_keys_write_only(client):
    data = saved(client, api_key=SECRET)
    profile_id = data["saved_profile_id"]
    assert SECRET not in json.dumps(data)
    assert data["profiles"][0]["has_api_key"] is True
    response = client.post(BASE + "/active", json={"profile_id": profile_id, "revision": 1})
    assert response.status_code == 200
    response = client.put(
        BASE + f"/profiles/{profile_id}", json=body(name="改名", model="second-model", revision=2)
    )
    assert response.status_code == 200
    reloaded = ModelSettingsStore(deps.WORKSPACE_ROOT)
    assert reloaded.active().api_key.get_secret_value() == SECRET
    assert reloaded.active().options.model == "second-model"
    assert SECRET not in client.get(BASE).text
    assert (
        client.request("DELETE", BASE + f"/profiles/{profile_id}", json={"revision": 3}).status_code
        == 400
    )
    assert (
        client.post(BASE + "/active", json={"revision": 3, "profile_id": None}).status_code == 200
    )
    assert (
        client.request("DELETE", BASE + f"/profiles/{profile_id}", json={"revision": 4}).status_code
        == 200
    )
    assert reloaded.public()["profiles"] == []


def test_key_rotation_clear_and_destination_changes_are_explicit(client):
    data = saved(client, api_key=SECRET)
    profile_id = data["saved_profile_id"]
    other = body(revision=1, base_url="https://another.example.invalid/v1")
    assert client.put(BASE + f"/profiles/{profile_id}", json=other).status_code == 400
    assert client.post(BASE + "/test", json={**other, "profile_id": profile_id}).status_code == 400
    assert ModelSettingsStore(deps.WORKSPACE_ROOT).public()["revision"] == 1
    assert (
        client.put(
            BASE + f"/profiles/{profile_id}", json={**other, "api_key": "replacement-key"}
        ).status_code
        == 200
    )
    cleared = client.put(
        BASE + f"/profiles/{profile_id}", json={**other, "revision": 2, "clear_api_key": True}
    )
    assert cleared.json()["data"]["profiles"][0]["has_api_key"] is False
    assert (
        client.post(
            BASE + "/profiles", json=body(revision=3, api_key=SECRET, clear_api_key=True)
        ).status_code
        == 400
    )


def test_stale_revision_cannot_overwrite_a_key(client):
    data = saved(client, api_key=SECRET)
    response = client.put(
        BASE + "/profiles/" + data["saved_profile_id"], json=body(api_key="stale-key")
    )
    assert response.status_code == 409
    assert (
        ModelSettingsStore(deps.WORKSPACE_ROOT)
        .draft(ProfileInput(**body(revision=1)), data["saved_profile_id"])
        .api_key.get_secret_value()
        == SECRET
    )


def test_concurrent_writes_and_failed_atomic_replace_preserve_saved_data(tmp_path, monkeypatch):
    store = ModelSettingsStore(tmp_path)
    profile = ProfileInput(**body(api_key=SECRET))

    def write_once():
        try:
            return store.save(profile)
        except SettingsConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: write_once(), range(2)))
    assert len([result for result in results if result]) == 1
    assert len(store.public()["profiles"]) == 1
    before = store.path.read_bytes()

    def fail_replace(*args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(model_settings_store, "durable_replace", fail_replace)
    with pytest.raises(OSError):
        store.save(ProfileInput(**body(revision=1)))
    assert store.path.read_bytes() == before


def test_local_key_protection_and_corrupted_files_are_not_silently_overwritten(tmp_path):
    store = ModelSettingsStore(tmp_path)
    data = store.save(ProfileInput(**body(api_key=SECRET)))
    restored = store.draft(ProfileInput(**body(revision=1)), data["saved_profile_id"])
    assert restored.api_key.get_secret_value() == SECRET
    if os.name == "nt":
        assert SECRET not in store.path.read_text(encoding="utf-8")
        assert "dpapi:" in store.path.read_text(encoding="utf-8")
    else:
        assert store.directory.stat().st_mode & 0o777 == 0o700
        assert store.path.stat().st_mode & 0o777 == 0o600
    store.path.write_text('{"schema_version":99}', encoding="utf-8")
    with pytest.raises(ValueError, match="损坏"):
        store.save(ProfileInput(**body(revision=1)))
    assert store.path.read_text(encoding="utf-8") == '{"schema_version":99}'


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com",
        "https://" + f"name:{SECRET}@example.invalid/v1",  # Synthetic credential only.
        "https://example.com?key=secret",
        "https://example.com/#secret",
        "https://example.com\n/",
        "http://localhost:99999",
    ],
)
def test_invalid_endpoints_are_rejected_without_echoing_submitted_secrets(client, url):
    response = client.post(BASE + "/profiles", json=body(base_url=url, api_key=SECRET))
    assert response.status_code == 422
    assert SECRET not in response.text
    assert not deps.WORKSPACE_ROOT.exists()


def test_invalid_key_and_raw_json_are_never_echoed_in_validation_errors(client):
    response = client.post(BASE + "/profiles", json=body(api_key=SECRET + "\nInjected: header"))
    assert response.status_code == 422 and SECRET not in response.text
    response = client.post(
        BASE + "/profiles",
        content='{"api_key":"' + SECRET,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422 and SECRET not in response.text


def test_settings_reject_foreign_origins_dns_rebinding_and_form_posts(client):
    for headers in (
        {"Origin": "https://foreign.invalid"},
        {"Host": "foreign.invalid"},
        {"X-Model-Settings": ""},
    ):
        assert client.get(BASE, headers=headers).status_code == 403
    assert client.post(BASE + "/profiles", data={"name": "unsafe"}).status_code == 415
    assert not deps.WORKSPACE_ROOT.exists()
    assert client.get(BASE, headers={"Origin": "http://127.0.0.1:5173"}).status_code == 200


def test_settings_reject_remote_clients_and_demo_writes(client, monkeypatch):
    with TestClient(
        app,
        base_url="http://localhost",
        client=("192.0.2.1", 1234),
        headers={"X-Model-Settings": "1"},
    ) as remote:
        assert remote.get(BASE).status_code == 403
    monkeypatch.setenv("NOVELWB_MODEL_SETTINGS_DISABLED", "1")
    assert client.get(BASE).json()["data"]["disabled"] is True
    assert client.post(BASE + "/profiles", json=body()).status_code == 403


@pytest.mark.parametrize(
    "protocol,path,header",
    [
        ("openai", "/proxy/v1/chat/completions", "authorization"),
        ("deepseek", "/proxy/v1/chat/completions", "authorization"),
        ("openai_responses", "/proxy/v1/responses", "authorization"),
        ("anthropic", "/proxy/v1/messages", "x-api-key"),
        ("gemini", "/proxy/v1/models/test-model:generateContent", "x-goog-api-key"),
    ],
)
def test_protocol_requests_use_selected_model_and_parse_usage(monkeypatch, protocol, path, header):
    requests = []

    def handler(request):
        requests.append(request)
        if protocol == "anthropic":
            data = {
                "content": [{"type": "text", "text": "OK"}],
                "usage": {"input_tokens": 10, "output_tokens": 3},
            }
        elif protocol == "gemini":
            data = {
                "candidates": [
                    {"content": {"parts": [{"thought": True, "text": "hidden"}, {"text": "OK"}]}}
                ],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 2,
                    "thoughtsTokenCount": 1,
                },
            }
        elif protocol == "openai_responses":
            data = {
                "output": [
                    {"type": "reasoning"},
                    {"type": "message", "content": [{"type": "output_text", "text": "OK"}]},
                ],
                "usage": {"input_tokens": 10, "output_tokens": 3},
            }
        else:
            data = completion()
        return httpx.Response(200, json=data)

    clients = install_transport(monkeypatch, handler)
    profile = ResolvedProfile(
        ProfileInput(
            **body(
                protocol=protocol, max_output_tokens=512, token_parameter="max_completion_tokens"
            )
        ).options(),
        SecretStr(SECRET),
    )
    result = ConfiguredAdapter(profile).call(
        "JSON prompt",
        step_id="test",
        prompt_key="test",
        prompt_version="1",
        prompt_hash="hash",
        model="legacy-deepseek-model",
        max_tokens=4096,
        thinking="enabled",
        reasoning_effort="max",
        response_format="json_object",
    )
    assert result.text == "OK"
    assert result.record.model == "test-model"
    assert (result.record.input_tokens, result.record.output_tokens) == (10, 3)
    request = requests[0]
    assert request.url.path == path
    assert SECRET in request.headers[header] and SECRET not in str(request.url)
    payload = json.loads(request.content)
    assert "legacy-deepseek-model" not in str(payload)
    assert "temperature" not in payload
    if protocol == "gemini":
        assert payload["generationConfig"] == {
            "maxOutputTokens": 512,
            "responseMimeType": "application/json",
        }
    else:
        assert payload["model"] == "test-model"
    if protocol in {"openai", "deepseek"}:
        assert payload["max_completion_tokens"] == 512
        assert payload["response_format"]["type"] == "json_object"
    if protocol == "deepseek":
        assert payload["thinking"] == {"type": "enabled"}
    else:
        assert "thinking" not in payload and "reasoning_effort" not in payload
    assert clients[0]["trust_env"] is False
    assert clients[0]["follow_redirects"] is False


def test_full_endpoint_normalization_and_disabled_json_parameters(monkeypatch):
    requests = []
    install_transport(
        monkeypatch,
        lambda request: (requests.append(request), httpx.Response(200, json=completion()))[1],
    )
    profile = ProfileInput(
        **body(
            base_url="http://localhost:11434/v1/chat/completions/",
            json_mode=False,
            send_temperature=True,
        )
    ).options()
    ConfiguredAdapter(ResolvedProfile(profile, SecretStr(""))).call(
        "JSON",
        step_id="a",
        prompt_key="a",
        prompt_version="1",
        prompt_hash="a",
        response_format="json_object",
    )
    assert requests[0].url.path == "/v1/chat/completions"
    assert "authorization" not in requests[0].headers
    payload = json.loads(requests[0].content)
    assert "response_format" not in payload and payload["temperature"] == 0.7


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 302])
def test_connection_failure_is_redacted_bounded_and_does_not_save(client, monkeypatch, status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, text=SECRET, headers={"Location": "https://foreign.invalid"})

    clients = install_transport(monkeypatch, handler)
    response = client.post(BASE + "/test", json=body(api_key=SECRET, max_retries=2))
    assert response.status_code == 502
    assert SECRET not in response.text and str(status) in response.text
    assert len(requests) == 1 and clients[0]["timeout"] <= 20
    assert not deps.WORKSPACE_ROOT.exists()


def test_connection_test_can_reuse_saved_secret_without_returning_provider_output(
    client, monkeypatch
):
    data = saved(client, api_key=SECRET)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=completion(SECRET))

    install_transport(monkeypatch, handler)
    response = client.post(
        BASE + "/test", json={**body(revision=1), "profile_id": data["saved_profile_id"]}
    )
    assert response.status_code == 200 and SECRET not in response.text
    assert requests[0].headers["authorization"] == "Bearer " + SECRET
    assert ModelSettingsStore(deps.WORKSPACE_ROOT).public()["active_profile_id"] is None


@pytest.mark.parametrize(
    "bad_response", ["not-json", {}, {"choices": []}, {"choices": [{"message": {"content": ""}}]}]
)
def test_incompatible_and_empty_responses_fail_with_actionable_messages(monkeypatch, bad_response):
    install_transport(
        monkeypatch,
        lambda request: (
            httpx.Response(200, text=bad_response)
            if isinstance(bad_response, str)
            else httpx.Response(200, json=bad_response)
        ),
    )
    adapter = ConfiguredAdapter(ResolvedProfile(ProfileInput(**body()).options(), SecretStr("")))
    with pytest.raises(ModelConnectionError):
        adapter.test_connection()


def test_timeout_message_cannot_expose_request_details(client, monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout(SECRET, request=request)

    install_transport(monkeypatch, timeout)
    response = client.post(BASE + "/test", json=body(api_key=SECRET))
    assert response.status_code == 502 and SECRET not in response.text


def test_activation_and_edit_bind_new_orchestrators_without_changing_old_runs(client, monkeypatch):
    assert client.post("/projects", json={"project_id": "selection"}).status_code == 200
    fallback = deps.get_orchestrator("selection")
    assert fallback._deps.llm.adapter_type == "mock_replay"
    data = saved(client, api_key=SECRET)
    profile_id = data["saved_profile_id"]
    client.post(BASE + "/active", json={"profile_id": profile_id, "revision": 1})
    old_run = deps.get_orchestrator("selection")
    client.put(BASE + f"/profiles/{profile_id}", json=body(revision=2, model="replacement-model"))
    new_run = deps.get_orchestrator("selection")
    requests = []
    install_transport(
        monkeypatch,
        lambda request: (
            requests.append(json.loads(request.content)),
            httpx.Response(200, json=completion()),
        )[1],
    )
    for orch in (old_run, new_run):
        orch._deps.llm.call(
            "JSON",
            step_id="step",
            prompt_key="key",
            prompt_version="1",
            prompt_hash="h",
            model="deepseek-v4-pro",
        )
    assert [request["model"] for request in requests] == ["test-model", "replacement-model"]
    assert old_run is not new_run
    monkeypatch.setenv("NOVELWB_MODEL_SETTINGS_DISABLED", "1")
    assert deps.get_orchestrator("selection")._deps.llm.adapter_type == "mock_replay"


def test_profile_is_used_by_the_actual_foundation_workflow(client, monkeypatch):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/mock/graph1_spec00.json").read_text(encoding="utf-8")
    )
    client.post("/projects", json={"project_id": "configured_workflow"})
    data = saved(client, api_key=SECRET, model="my-selected-model")
    client.post(BASE + "/active", json={"profile_id": data["saved_profile_id"], "revision": 1})
    requests = []
    install_transport(
        monkeypatch,
        lambda request: (
            requests.append(json.loads(request.content)),
            httpx.Response(200, json=completion(fixture["response_text"])),
        )[1],
    )
    orch = deps.get_orchestrator("configured_workflow")
    review = orch.generate_workflow_review(
        run_id="run_configured", stage="foundation", brief="渡口停航，药船必须付出代价抵达目的地。"
    )
    artifacts = review["editable"]["artifacts"]
    assert len(artifacts) == 1 and artifacts[0]["artifact_key"] == "spec00"
    assert artifacts[0]["content"]["main_promise"] == "通过付出代价查清渡口停航原因"
    assert requests and all(request["model"] == "my-selected-model" for request in requests)
    assert SECRET not in json.dumps(review)


def test_switch_during_generation_cannot_create_duplicate_pending_reviews(client, monkeypatch):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/mock/graph1_spec00.json").read_text(encoding="utf-8")
    )
    client.post("/projects", json={"project_id": "switch_during_generation"})
    data = saved(client, api_key=SECRET, model="old-model")
    profile_id = data["saved_profile_id"]
    client.post(BASE + "/active", json={"profile_id": profile_id, "revision": 1})
    old_run = deps.get_orchestrator("switch_during_generation")
    response = client.put(
        BASE + f"/profiles/{profile_id}", json=body(revision=2, model="new-model")
    )
    assert response.status_code == 200
    new_run = deps.get_orchestrator("switch_during_generation")
    entered = threading.Event()
    second_entered = threading.Event()
    second_started = threading.Event()
    release = threading.Event()
    calls = []

    def provider(request):
        calls.append(json.loads(request.content)["model"])
        (entered if len(calls) == 1 else second_entered).set()
        assert release.wait(5)
        return httpx.Response(200, json=completion(fixture["response_text"]))

    install_transport(monkeypatch, provider)

    def generate(orch, run_id):
        if run_id == "run_new":
            second_started.set()
        try:
            return orch.generate_workflow_review(
                run_id=run_id, stage="foundation", brief="渡口停航，药船必须付出代价抵达目的地。"
            )
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(generate, old_run, "run_old")
        try:
            assert entered.wait(3)
            second = pool.submit(generate, new_run, "run_new")
            assert second_started.wait(3)
            assert not second_entered.wait(0.2)
        finally:
            release.set()
        assert first.result(timeout=5)["editable"]["artifacts"][0]["artifact_key"] == "spec00"
        assert "等待审核" in second.result(timeout=5)
    assert calls == ["old-model"]
    pending = [
        packet
        for packet in new_run._staging_store.list_all()
        if packet.content.get("status") == "pending"
    ]
    assert len(pending) == 1
