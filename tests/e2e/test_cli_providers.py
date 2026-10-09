"""Live providers through `bench run`, each on a mock transport (protocol)."""

import functools
import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import npcbench.cli as cli
from npcbench.cli import app

FIX = Path(__file__).parents[1] / "fixtures" / "s1"
runner = CliRunner()


def _run(tmp_path, provider, *extra):
    return runner.invoke(
        app,
        [
            "run",
            "--scenarios",
            str(FIX / "scenarios.yaml"),
            "--character",
            str(FIX / "character.yaml"),
            "--prompt",
            str(FIX / "prompt.md"),
            "--provider",
            provider,
            "--model",
            "qwen3:4b",
            "--run-id",
            "r1",
            "--results-dir",
            str(tmp_path / "results"),
            *extra,
        ],
    )


def _ollama_http():
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "qwen3:4b", "digest": "sha256:d1"}]}
            )
        lines = [
            {"message": {"content": "Coin first."}, "done": False},
            {"done": True, "done_reason": "stop", "prompt_eval_count": 9, "eval_count": 3},
        ]
        return httpx.Response(200, text="".join(json.dumps(x) + "\n" for x in lines))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_an_ollama_run_records_the_model_digest_and_replays_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cli, "OllamaClient", functools.partial(cli.OllamaClient, http=_ollama_http())
    )
    result = _run(tmp_path, "ollama")
    assert result.exit_code == 0, result.output
    run_dir = tmp_path / "results" / "r1"
    attempts = [json.loads(line) for line in (run_dir / "recordings.jsonl").open()]
    assert {a["model_version"] for a in attempts} == {"qwen3:4b@sha256:d1 (unknown)"}
    assert {a["response_text"] for a in attempts} == {"Coin first."}
    config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
    assert config["provider"] == "ollama"
    monkeypatch.undo()  # replay never builds a client
    replay = runner.invoke(
        app, ["replay", "--run-id", "r1", "--results-dir", str(tmp_path / "results")]
    )
    assert replay.exit_code == 0, replay.output


def test_a_provider_configuration_error_stops_the_run_cleanly(tmp_path, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"models": []})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(cli, "OllamaClient", functools.partial(cli.OllamaClient, http=http))
    result = _run(tmp_path, "ollama")
    assert result.exit_code == 1
    assert "not in the local Ollama store" in result.output
    assert not (tmp_path / "results" / "r1").exists()


def test_an_unknown_provider_is_refused(tmp_path):
    result = _run(tmp_path, "mystery")
    assert result.exit_code == 1
    assert "mystery" in result.output


KEY = "sk-ant-test-e2e-SECRET"


def _anthropic_http():
    events = [
        {
            "type": "message_start",
            "message": {"model": "claude-pin-1", "usage": {"input_tokens": 9}},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Coin."},
        },
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 2},
        },
        {"type": "message_stop"},
    ]
    text = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)
    return httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=text))
    )


def test_an_anthropic_run_pins_reasoning_and_never_writes_the_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setattr(
        cli, "AnthropicClient", functools.partial(cli.AnthropicClient, http=_anthropic_http())
    )
    result = _run(tmp_path, "anthropic", "--reasoning", "lowest")
    assert result.exit_code == 0, result.output
    run_dir = tmp_path / "results" / "r1"
    config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
    assert config["provider"] == "anthropic"
    assert config["reasoning"] == {"setting": "lowest", "thinking": "effort low", "disabled": False}
    attempts = [json.loads(line) for line in (run_dir / "recordings.jsonl").open()]
    assert {a["model_version"] for a in attempts} == {
        "claude-pin-1 (reasoning: lowest effort; cannot be disabled)"
    }
    for path in run_dir.iterdir():
        assert KEY not in path.read_text(encoding="utf-8"), path.name
    assert KEY not in result.output


def test_an_anthropic_run_without_a_key_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = _run(tmp_path, "anthropic")
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output
    assert not (tmp_path / "results" / "r1").exists()


@pytest.mark.parametrize(
    "provider,model",
    [
        ("openai", "gpt-4.1-mini-2025-04-14"),
        ("groq", "qwen/qwen3.8-27b"),
        ("gemini", "gemini-2.5-flash-lite"),
    ],
)
def test_chat_completions_record_and_replay_without_credentials(
    tmp_path, monkeypatch, provider, model
):
    key = "test-new-provider-SECRET"
    monkeypatch.setenv(f"{provider.upper()}_API_KEY", key)

    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == model
        events = [
            {
                "model": model,
                "choices": [
                    {"index": 0, "delta": {"content": "Coin first."}, "finish_reason": None}
                ],
            },
            {
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            },
        ]
        text = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
        return httpx.Response(200, text=text)

    monkeypatch.setattr(
        cli,
        "ChatCompletionsClient",
        functools.partial(
            cli.ChatCompletionsClient, http=httpx.Client(transport=httpx.MockTransport(handler))
        ),
    )
    # Last --model wins, overriding the existing helper's local fixture model.
    result = _run(tmp_path, provider, "--model", model)
    assert result.exit_code == 0, result.output
    run_dir = tmp_path / "results" / "r1"
    config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
    assert config["provider"] == provider
    assert config["reasoning"]["disabled"] is True
    assert config["request_interval_seconds"] == 0
    assert config["reply_token_cap"] == 512
    for path in run_dir.iterdir():
        assert key not in path.read_text(encoding="utf-8")
    assert key not in result.output
    monkeypatch.undo()
    replay = runner.invoke(
        app, ["replay", "--run-id", "r1", "--results-dir", str(tmp_path / "results")]
    )
    assert replay.exit_code == 0, replay.output


@pytest.mark.parametrize("provider", ["openai", "groq", "gemini"])
def test_chat_completions_missing_key_is_a_clean_cli_error(tmp_path, monkeypatch, provider):
    variable = f"{provider.upper()}_API_KEY"
    monkeypatch.delenv(variable, raising=False)
    result = _run(tmp_path, provider)
    assert result.exit_code == 1
    assert variable in result.output
    assert not (tmp_path / "results" / "r1").exists()
