"""Zero-heavy-import guards: okf serializer chain must stay import-clean.

Phase 19 debt wave (lazy heavy imports). Before the fix, ingestion/bundle.py
imported docling + llama_index at module top level, so importing
llamaindex_runtime.okf.serializer (via the ingestion package __init__)
pulled torch/transformers into sys.modules and broke the entity
zero-heavy-import guards whenever okf shared a pytest process.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLE_PATH = REPO_ROOT / "llamaindex_runtime" / "ingestion" / "bundle.py"

HEAVY_MODULES = (
    "docling",
    "llama_index",
    "torch",
    "transformers",
    "modelscope",
    "tokenizers",
    "sentencepiece",
)


def _probe_source(module: str) -> str:
    lines = [
        "import json, sys",
        "heavy = " + repr(HEAVY_MODULES),
        "import " + module,
        "hits = sorted(",
        "    m for m in sys.modules for h in heavy if m == h or m.startswith(h + '.')",
        ")",
        "print(json.dumps(hits))",
        "sys.exit(1 if hits else 0)",
    ]
    return "\n".join(lines) + "\n"


def _run_probe(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=180,
    )


def _assert_heavy_free(proc: subprocess.CompletedProcess[str], module: str) -> None:
    assert proc.returncode == 0, (
        f"importing {module!r} pulled heavy modules into sys.modules: "
        f"stdout={proc.stdout!r} stderr={proc.stderr[-2000:]!r}"
    )


def test_okf_serializer_import_is_heavy_free():
    proc = _run_probe(_probe_source("llamaindex_runtime.okf.serializer"))
    _assert_heavy_free(proc, "llamaindex_runtime.okf.serializer")


def test_ingestion_package_import_is_heavy_free():
    proc = _run_probe(_probe_source("llamaindex_runtime.ingestion"))
    _assert_heavy_free(proc, "llamaindex_runtime.ingestion")


def test_docling_ingestor_import_is_heavy_free():
    proc = _run_probe(_probe_source("llamaindex_runtime.ingestion.docling_ingestor"))
    _assert_heavy_free(proc, "llamaindex_runtime.ingestion.docling_ingestor")


def test_build_with_injected_converter_never_imports_docling():
    lines = [
        "import json, sys, tempfile",
        "from pathlib import Path",
        "import llamaindex_runtime.ingestion.bundle as bundle_mod",
        "class _FakeDocument:",
        "    def export_to_dict(self):",
        "        return {'fake': True}",
        "    def export_to_markdown(self, image_placeholder=''):",
        "        return '# fake md'",
        "class _FakeResult:",
        "    document = _FakeDocument()",
        "class _FakeConverter:",
        "    def convert(self, source):",
        "        return _FakeResult()",
        "tmp = Path(tempfile.mkdtemp()) / 'doc.md'",
        "tmp.write_text('# hello', encoding='utf-8')",
        "b = bundle_mod.build_docling_bundle(tmp, converter=_FakeConverter())",
        "assert len(b.json_documents) == 1 and len(b.markdown_documents) == 1",
        "assert b.json_documents[0].text == json.dumps({'fake': True})",
        "assert b.markdown_documents[0].text == '# fake md'",
        "assert b.source_path.name == 'doc.md'",
        "assert 'docling' not in sys.modules, 'docling must stay unimported when converter is injected'",
        "print('OK')",
    ]
    proc = _run_probe("\n".join(lines) + "\n")
    assert proc.returncode == 0, (
        f"injected-converter bundle build broken or docling imported: "
        f"stdout={proc.stdout!r} stderr={proc.stderr[-2000:]!r}"
    )


def test_bundle_module_has_no_top_level_heavy_imports():
    tree = ast.parse(BUNDLE_PATH.read_text(encoding="utf-8"))
    offenders = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            if name.split(".")[0] in {"docling", "llama_index"}:
                offenders.append(name)
    assert offenders == [], (
        f"bundle.py must not import heavy libraries at module top level: {offenders}"
    )