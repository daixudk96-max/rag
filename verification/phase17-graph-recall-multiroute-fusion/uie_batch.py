"""UIE batch extraction via a worker subprocess (Phase 17 Wave 2).

Loads the wave-1 acceptance runner module through importlib to reuse
its frozen extraction DTOs, and exposes the subprocess-backed batch
extractor plus its Protocol seam.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

_RUNNER_PATH: Path = Path(__file__).resolve().parent / "run_graph_recall_acceptance.py"


def _load_runner() -> Any:
    """Load the wave-1 acceptance runner module via importlib by path."""
    spec = importlib.util.spec_from_file_location(
        "run_graph_recall_acceptance", _RUNNER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load run_graph_recall_acceptance module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


class SubprocessUieBatchExtractor:
    """Batch extractor that shells out to a UIE worker subprocess."""

    def __init__(
        self, venv_python: str, worker_script: str, *, timeout_s: float = 600.0
    ) -> None:
        for label, raw in (
            ("venv_python", venv_python),
            ("worker_script", worker_script),
        ):
            resolved = Path(raw)
            if not resolved.is_absolute():
                raise ValueError(f"{label} must be an absolute path: {raw!r}")
            if not resolved.is_file():
                raise ValueError(f"{label} does not exist: {raw!r}")
        self.venv_python = venv_python
        self.worker_script = worker_script
        self.timeout_s = timeout_s

    def extract(self, texts: Sequence[str]) -> Any:
        argv = [str(self.venv_python), str(self.worker_script)]
        # W7 review (Security-1): the UIE worker needs no credentials;
        # strip provider key prefixes from the inherited environment.
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("OPENAI_", "DASHSCOPE_"))
        }
        proc = subprocess.run(
            argv,
            input=json.dumps({"texts": [str(t) for t in texts]}).encode("utf-8"),
            capture_output=True,
            check=False,
            timeout=self.timeout_s,
            env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError("uie extraction worker failed")
        body = json.loads(proc.stdout.decode("utf-8"))
        documents: list[Any] = []
        for entry in body["documents"]:
            documents.append(
                runner.DocumentExtraction(
                    document_id=str(entry["document_id"]),
                    source_text=str(entry["source_text"]),
                    normalized_text=str(entry["normalized_text"]),
                    entities=tuple(
                        runner.ExtractionEntity(
                            text=str(e["text"]),
                            label=str(e["label"]),
                            char_start=int(e["char_start"]),
                            char_end=int(e["char_end"]),
                            confidence=e.get("confidence"),
                        )
                        for e in entry["entities"]
                    ),
                    relations=tuple(
                        runner.ExtractionRelation(
                            subject_text=str(r["subject_text"]),
                            subject_type=str(r["subject_type"]),
                            relation=str(r["relation"]),
                            object_text=str(r["object_text"]),
                            object_type=str(r["object_type"]),
                            source_text=str(r["source_text"]),
                        )
                        for r in entry["relations"]
                    ),
                )
            )
        return runner.ExtractionBundle(documents=tuple(documents))


class UieBatchExtractor(Protocol):
    """Extraction seam: texts in, runner.ExtractionBundle DTO out."""

    def extract(self, texts: Sequence[str]) -> Any: ...
