from __future__ import annotations

import io
import json
import queue
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.run_sonarlint_ls_probe import JsonRpcEndpoint, run_probe


class _FakeBinaryStdout:
    def __init__(self, payload: bytes) -> None:
        self._buffer = io.BytesIO(payload)

    def readline(self) -> bytes:
        return self._buffer.readline()

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


class _FakeBinaryStdin:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        return None


class _FakeProcess:
    def __init__(self, stdout_payload: bytes = b"") -> None:
        self.stdout = _FakeBinaryStdout(stdout_payload)
        self.stdin = _FakeBinaryStdin()
        self.stderr = io.BytesIO()
        self.terminated = False
        self.waited = False
        self.killed = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        return 0

    def kill(self) -> None:
        self.killed = True


def _encode_message(payload: dict) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body


def test_read_loop_handles_two_back_to_back_messages_without_jsondecodeerror() -> None:
    first = {"jsonrpc": "2.0", "method": "window/logMessage", "params": {"message": "ascii"}}
    second = {"jsonrpc": "2.0", "method": "window/logMessage", "params": {"message": "第二条消息"}}
    payload = _encode_message(first) + _encode_message(second)

    endpoint = JsonRpcEndpoint(_FakeProcess(payload))

    first_msg = endpoint.recv(timeout=1.0)
    second_msg = endpoint.recv(timeout=1.0)

    assert first_msg is not None
    assert second_msg is not None
    assert first_msg.payload == first
    assert second_msg.payload == second


def test_send_uses_byte_length_for_utf8_payloads() -> None:
    process = _FakeProcess()
    endpoint = JsonRpcEndpoint(process)

    endpoint.send({"jsonrpc": "2.0", "method": "window/logMessage", "params": {"message": "第二条消息"}})

    assert process.stdin.writes
    wire = process.stdin.writes[0]
    header, body = wire.split(b"\r\n\r\n", 1)
    assert header == b"Content-Length: " + str(len(body)).encode("ascii")


class _FakeEndpoint:
    def __init__(self, messages: list[dict]) -> None:
        self._messages = queue.Queue()
        for message in messages:
            self._messages.put(SimpleNamespace(payload=message))
        self.sent: list[dict] = []

    def send(self, payload: dict) -> None:
        self.sent.append(payload)

    def recv(self, timeout: float) -> SimpleNamespace | None:
        try:
            return self._messages.get_nowait()
        except queue.Empty:
            return None


def test_run_probe_returns_zero_when_analysis_starts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    target.write_text("def f(x):\n    return eval(x)\n", encoding="utf-8")

    messages = [
        {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}},
        {"jsonrpc": "2.0", "method": "workspace/configuration", "id": 2, "params": {"items": [{"section": "sonarlint"}]}},
        {"jsonrpc": "2.0", "method": "window/logMessage", "params": {"type": 4, "message": "Starting analysis with configuration: []"}},
    ]

    fake_process = _FakeProcess()
    monkeypatch.setattr("scripts.run_sonarlint_ls_probe._start_process", lambda: fake_process)
    monkeypatch.setattr("scripts.run_sonarlint_ls_probe.JsonRpcEndpoint", lambda process: _FakeEndpoint(messages))

    result = run_probe(target)

    assert result == 0


def test_run_probe_red_regression_for_extra_data_crash(tmp_path: Path) -> None:
    first = {"jsonrpc": "2.0", "method": "window/logMessage", "params": {"message": "ascii"}}
    second = {"jsonrpc": "2.0", "method": "window/logMessage", "params": {"message": "第二条消息"}}
    payload = _encode_message(first) + _encode_message(second)

    endpoint = JsonRpcEndpoint(_FakeProcess(payload))

    messages = []
    for _ in range(2):
        msg = endpoint.recv(timeout=1.0)
        assert msg is not None
        messages.append(msg.payload)

    assert messages == [first, second]


def test_run_probe_exits_zero_when_diagnostics_received_before_analysis_log_message(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Regression test: diagnostics can arrive before the 'Starting analysis' log message.

    The probe should return 0 (success) when diagnostics are received for the target file,
    even if the 'Starting analysis with configuration' log message hasn't been seen yet.
    """
    target = tmp_path / "demo.py"
    target.write_text("def f(x):\n    return eval(x)\n", encoding="utf-8")

    # Messages in order: initialize response, then diagnostics WITHOUT the log message
    messages = [
        {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}},
        {"jsonrpc": "2.0", "method": "workspace/configuration", "id": 2, "params": {"items": [{"section": "sonarlint"}]}},
        {"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics", "params": {"uri": target.as_uri(), "diagnostics": [{"code": "python:SXXX", "severity": 2, "message": "Security issue"}]}},
    ]

    fake_process = _FakeProcess()
    monkeypatch.setattr("scripts.run_sonarlint_ls_probe._start_process", lambda: fake_process)
    monkeypatch.setattr("scripts.run_sonarlint_ls_probe.JsonRpcEndpoint", lambda process: _FakeEndpoint(messages))

    result = run_probe(target)

    # Should return 0 because diagnostics were received for target file
    # NOT 2 which would indicate analysis never started
    assert result == 0


def test_run_probe_exits_zero_when_both_diagnostics_and_log_message_arrive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test that the probe handles the normal case where both log message and diagnostics arrive."""
    target = tmp_path / "demo.py"
    target.write_text("def f(x):\n    return eval(x)\n", encoding="utf-8")

    # Messages in order: initialize response, log message, then diagnostics
    messages = [
        {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}},
        {"jsonrpc": "2.0", "method": "workspace/configuration", "id": 2, "params": {"items": [{"section": "sonarlint"}]}},
        {"jsonrpc": "2.0", "method": "window/logMessage", "params": {"type": 4, "message": "Starting analysis with configuration: []"}},
        {"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics", "params": {"uri": target.as_uri(), "diagnostics": [{"code": "python:SXXX", "severity": 2, "message": "Security issue"}]}},
    ]

    fake_process = _FakeProcess()
    monkeypatch.setattr("scripts.run_sonarlint_ls_probe._start_process", lambda: fake_process)
    monkeypatch.setattr("scripts.run_sonarlint_ls_probe.JsonRpcEndpoint", lambda process: _FakeEndpoint(messages))

    result = run_probe(target)

    # Should return 0 because analysis_started was set AND diagnostics were received
    assert result == 0
