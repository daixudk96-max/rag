from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


JAVA_PATH = Path(r"C:\Users\daixu\.cursor\extensions\sonarsource.sonarlint-vscode-5.2.3-win32-x64\jre\21.0.10-win32-x86_64.tar\bin\java.exe")
LS_JAR = Path(r"C:\Users\daixu\.cursor\extensions\sonarsource.sonarlint-vscode-5.2.3-win32-x64\server\sonarlint-ls.jar")
ANALYZERS = [
    Path(r"C:\Users\daixu\.cursor\extensions\sonarsource.sonarlint-vscode-5.2.3-win32-x64\analyzers\sonarpython.jar"),
    Path(r"C:\Users\daixu\.cursor\extensions\sonarsource.sonarlint-vscode-5.2.3-win32-x64\analyzers\sonartext.jar"),
]


@dataclass
class RpcMessage:
    payload: dict[str, Any]


class JsonRpcEndpoint:
    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self._process = process
        self._queue: queue.Queue[RpcMessage] = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        assert self._process.stdout is not None
        while True:
            headers: dict[str, str] = {}
            while True:
                line = self._process.stdout.readline()
                if line == b"":
                    return
                stripped = line.strip()
                if not stripped:
                    break
                if b":" in stripped:
                    key, value = stripped.split(b":", 1)
                    headers[key.strip().lower().decode("ascii")] = value.strip().decode("utf-8")
            content_length = int(headers.get("content-length", "0"))
            if content_length <= 0:
                continue
            body = self._process.stdout.read(content_length)
            if not body:
                return
            payload = json.loads(body.decode("utf-8"))
            self._queue.put(RpcMessage(payload=payload))

    def send(self, payload: dict[str, Any]) -> None:
        assert self._process.stdin is not None
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        wire = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
        self._process.stdin.write(wire)
        self._process.stdin.flush()

    def recv(self, timeout: float) -> RpcMessage | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None


def _list_files_in_folder(folder_uri: str) -> dict[str, list[dict[str, str | None]]]:
    folder = Path(folder_uri.removeprefix("file:///").replace("/", "\\"))
    if not folder.exists():
        return {"foundFiles": []}

    found_files: list[dict[str, str | None]] = []
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        content: str | None = None
        if path.name in {"sonar-project.properties", ".sonarcloud.properties"} or path.suffix == ".json":
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                content = None
        found_files.append(
            {
                "fileName": path.name,
                "filePath": str(path),
                "content": content,
            }
        )
    return {"foundFiles": found_files}


def _start_process() -> subprocess.Popen[bytes]:
    cmd = [
        str(JAVA_PATH),
        "-jar",
        str(LS_JAR),
        "-stdio",
        *(f"-analyzers={path}" for path in ANALYZERS),
    ]
    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        bufsize=0,
    )


def run_probe(target_file: Path) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    telemetry_dir = repo_root / ".sonarlint_usage"
    telemetry_dir.mkdir(exist_ok=True)
    process = _start_process()
    endpoint = JsonRpcEndpoint(process)

    target_file = target_file.resolve()
    target_uri = target_file.as_uri()
    file_text = target_file.read_text(encoding="utf-8")

    endpoint.send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "processId": None,
                "rootUri": repo_root.as_uri(),
                "capabilities": {
                    "workspace": {"configuration": True},
                    "textDocument": {"publishDiagnostics": {"relatedInformation": True}},
                },
                "workspaceFolders": [
                    {"uri": repo_root.as_uri(), "name": repo_root.name}
                ],
                "initializationOptions": {
                    "productKey": "vscode",
                    "telemetryStorage": str(telemetry_dir),
                    "productName": "SonarLint VSCode",
                    "productVersion": "5.2.3",
                    "workspaceName": repo_root.name,
                    "firstSecretDetected": False,
                    "showVerboseLogs": True,
                    "platform": sys.platform,
                    "architecture": "amd64",
                    "additionalAttributes": {"vscode": {"uiKind": "Desktop", "isTelemetryEnabled": False}},
                    "enableNotebooks": True,
                    "clientNodePath": None,
                    "eslintBridgeServerPath": str(repo_root),
                    "connections": {"sonarqube": [], "sonarcloud": []},
                    "rules": {},
                    "focusOnNewCode": False,
                    "automaticAnalysis": True
                },
                "clientInfo": {"name": "claude-code-probe", "version": "1.0"},
            },
        }
    )

    initialized = False
    diagnostics: list[dict[str, Any]] = []
    analysis_started = False
    fatal_backend_error = False
    deadline = time.time() + 30

    while time.time() < deadline:
        message = endpoint.recv(timeout=1.0)
        if message is None:
            continue
        payload = message.payload

        if payload.get("id") == 1:
            initialized = True
            endpoint.send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
            endpoint.send(
                {
                    "jsonrpc": "2.0",
                    "method": "workspace/didChangeConfiguration",
                    "params": {"settings": {}},
                }
            )
            endpoint.send(
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didOpen",
                    "params": {
                        "textDocument": {
                            "uri": target_uri,
                            "languageId": "python",
                            "version": 1,
                            "text": file_text,
                        }
                    },
                }
            )
            endpoint.send(
                {
                    "jsonrpc": "2.0",
                    "method": "sonarlint/analyseOpenFileIgnoringExcludes",
                    "params": {
                        "triggeredByUser": True,
                        "textDocument": {
                            "uri": target_uri,
                            "languageId": "python",
                            "text": file_text,
                            "version": 1,
                        },
                        "notebookUri": None,
                        "notebookVersion": None,
                        "notebookCells": None,
                    },
                }
            )
            continue

        method = payload.get("method")
        if method:
            print(f"EVENT|method={method}")
            if method in {"workspace/configuration", "window/logMessage", "sonarlint/settingsApplied"}:
                print("EVENT_PARAMS|" + json.dumps(payload.get("params"), ensure_ascii=False))
                params = payload.get("params") or {}
                if method == "window/logMessage":
                    message = params.get("message", "") if isinstance(params, dict) else ""
                    if "Starting analysis with configuration" in message:
                        analysis_started = True
                    if "Could not initialize SonarLint Backend" in message:
                        fatal_backend_error = True
        if method == "workspace/configuration":
            items = payload.get("params", {}).get("items", [])
            result: list[dict[str, Any] | None] = []
            for item in items:
                section = item.get("section")
                if section == "sonarlint":
                    result.append(
                        {
                            "output": {"showVerboseLogs": True},
                            "connectedMode": {"connections": {"sonarqube": [], "sonarcloud": []}},
                            "rules": {},
                            "focusOnNewCode": False,
                            "automaticAnalysis": True,
                            "pathToNodeExecutable": None,
                        }
                    )
                elif section == "files.exclude":
                    result.append({})
                else:
                    result.append(None)
            endpoint.send(
                {
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": result,
                }
            )
            continue

        if method == "sonarlint/isOpenInEditor":
            print("EVENT_PARAMS|" + json.dumps(payload.get("params"), ensure_ascii=False))
            endpoint.send(
                {
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": True,
                }
            )
            continue

        if method == "sonarlint/listFilesInFolder":
            folder_uri = payload.get("params", {}).get("folderUri", "")
            endpoint.send(
                {
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": _list_files_in_folder(folder_uri),
                }
            )
            continue

        if method == "sonarlint/getJavaConfig":
            endpoint.send(
                {
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {},
                }
            )
            continue

        if method == "sonarlint/isIgnoredByScm":
            endpoint.send(
                {
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": False,
                }
            )
            continue

        if method == "textDocument/publishDiagnostics":
            params = payload.get("params", {})
            if params.get("uri") == target_uri:
                diagnostics = params.get("diagnostics", [])
                analysis_started = True  # Diagnostics prove analysis was dispatched
                break
            continue

        if method and "id" in payload:
            endpoint.send(
                {
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": None,
                }
            )

    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        process.kill()

    if not initialized:
        print("SONARLINT_INIT_FAILED")
        if process.stderr is not None:
            err = process.stderr.read().decode("utf-8", errors="replace").strip()
            if err:
                print(err)
        return 1

    print(f"SONARLINT_DIAGNOSTIC_COUNT={len(diagnostics)}")
    for diagnostic in diagnostics:
        code = diagnostic.get("code")
        severity = diagnostic.get("severity")
        message = diagnostic.get("message", "")
        print(f"DIAG|code={code}|severity={severity}|message={message}")

    if fatal_backend_error:
        return 1
    if analysis_started:
        return 0
    return 2


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("verification/sonarlint_demo_issue.py")
    raise SystemExit(run_probe(target))
