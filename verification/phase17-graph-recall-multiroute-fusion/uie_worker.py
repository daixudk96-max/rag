"""Phase 17 UIE worker (W7-LIVE): prompt-driven extraction over PP-UIE-0.5B.

Reads a JSON payload {"texts": [...]} from stdin, runs the UIE v2
extraction loop (entity pass per schema type, relation pass per schema
gate, mirroring .tmp/uie2/eval8.py and .tmp/lightrag_compare/b2_extract.py
exactly) and writes the canonical bundle to stdout as JSON.

Paddle is imported ONLY inside main(); every helper above it is pure and
importable under the host interpreter so tests can drive build_documents
through faked infer seams with zero model dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import traceback
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

SCHEMA_FLAT = (
    "所在地",
    "所属公司",
    "任职于",
    "发布",
    "总部位于",
    "使用",
    "通话",
    "前往",
)
SCHEMA_GATE = {
    "人名": ("所在地", "所属公司", "任职于", "使用", "通话", "前往"),
    "公司名": ("发布", "总部位于"),
    "产品名": ("所属公司",),
    "地名": (),
    "其他": (),
}
ENTITY_TYPES = ("人名", "地名", "公司名", "产品名")
DEFAULT_MODEL_DIR = r"E:\github\rag\.cache\uie2-models\aistudio\PP-UIE-0.5B"
_SPLIT_RE = re.compile(r"[，,、;；|/]")

LLM_IE_PROMPT = (
    "你是一个阅读理解专家，请提取所给句子与问题，提取实体。请注意，如果存在实体，"
    "则一定在原句中逐字出现，请输出对应实体的原文，不要进行额外修改；如果无法提取，"
    "请输出“无相应实体”。\n"
    "**句子开始**\n"
    "{sentence}\n"
    "**句子结束**\n"
    "**问题开始**\n"
    "{prompt}\n"
    "**问题结束**\n"
    "**回答开始**\n"
)


def split_items(result_text: str) -> list[str]:
    """Split a UIE answer on the canonical separators, dropping markers."""
    if not result_text or result_text.strip() in ("无相应实体", "无"):
        return []
    parts = _SPLIT_RE.split(result_text)
    return [p.strip() for p in parts if p.strip() and p.strip() != "无相应实体"]


def map_to_entity(value: str, entity_texts: Sequence[str]) -> str | None:
    """Map a raw relation object back onto an extracted entity text."""
    if value in entity_texts:
        return value
    best: str | None = None
    for candidate in entity_texts:
        if candidate and candidate in value:
            if best is None or len(candidate) > len(best):
                best = candidate
    if best is not None:
        return best
    for candidate in entity_texts:
        if value and value in candidate:
            return candidate
    return None


def _relation_gate(entity_type: str) -> tuple[str, ...]:
    return SCHEMA_GATE.get(entity_type, ())


def build_documents(
    texts: Sequence[str], *, infer: Callable[[str, str], str]
) -> dict[str, Any]:
    """Run the two-pass extraction loop and return the canonical bundle."""
    digest = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()[:16]
    documents: list[dict[str, Any]] = []
    for index, text in enumerate(texts):
        type_of: dict[str, str] = {}
        entities: list[dict[str, Any]] = []
        seen_entities: set[tuple[str, str]] = set()
        for entity_type in ENTITY_TYPES:
            for item in split_items(infer(text, entity_type)):
                if item not in text:
                    continue
                key = (item, entity_type)
                if key in seen_entities:
                    continue
                seen_entities.add(key)
                start = text.index(item)
                entities.append(
                    {
                        "text": item,
                        "label": entity_type,
                        "char_start": start,
                        "char_end": start + len(item),
                        "confidence": None,
                    }
                )
                if item not in type_of:
                    type_of[item] = entity_type
        relations: list[dict[str, Any]] = []
        seen_triples: set[tuple[str, str, str]] = set()
        for entity in entities:
            for relation in _relation_gate(entity["label"]):
                raw = infer(text, entity["text"] + "的" + relation)
                for value in split_items(raw):
                    object_text = map_to_entity(value, [e["text"] for e in entities])
                    if object_text is None:
                        continue
                    if object_text == entity["text"]:
                        continue
                    triple_key = (entity["text"], relation, object_text)
                    if triple_key in seen_triples:
                        continue
                    seen_triples.add(triple_key)
                    relations.append(
                        {
                            "subject_text": entity["text"],
                            "subject_type": entity["label"],
                            "relation": relation,
                            "object_text": object_text,
                            "object_type": type_of[object_text],
                            "source_text": text,
                        }
                    )
        documents.append(
            {
                "document_id": str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL, f"phase17-uie-doc-{digest}-{index + 1}"
                    )
                ),
                "source_text": text,
                "normalized_text": text,
                "entities": entities,
                "relations": relations,
            }
        )
    return {"documents": documents}


def _resolve_model_dir() -> str:
    override = os.environ.get("PHASE17_UIE_MODEL_DIR")
    if not override:
        return DEFAULT_MODEL_DIR
    if not Path(override).is_absolute():
        raise ValueError("PHASE17_UIE_MODEL_DIR must be an absolute path")
    if not os.path.isdir(override):
        raise ValueError("PHASE17_UIE_MODEL_DIR does not exist: " + override)
    return override


def _run_stage(
    text: str,
    prompt: str,
    *,
    model: Any,
    tokenizer: Any,
) -> str:
    """One prompt -> generated text (single greedy sample), eval8 replica."""
    input_text = LLM_IE_PROMPT.format(sentence=text, prompt=prompt)
    if tokenizer.chat_template is not None:
        input_text = tokenizer.apply_chat_template(input_text, tokenize=False)
    feats = tokenizer(
        input_text,
        return_tensors="pd",
        return_position_ids=True,
        padding_side="left",
        padding=True,
        max_length=512,
        truncation=True,
        truncation_side="left",
        add_special_tokens=False,
    )
    outputs = model.generate(
        **feats,
        decode_strategy="greedy_search",
        top_k=1,
        top_p=1.0,
        temperature=1.0,
        max_new_tokens=50,
        bos_token_id=tokenizer.bos_token_id,
        eos_token_id=tokenizer.eos_token_id,
        pad_token_id=tokenizer.pad_token_id,
        num_return_sequences=1,
        use_cache=True,
    )
    res = tokenizer.decode(
        outputs[0][0].numpy().tolist(),
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )
    res = res.strip("\n")
    end_idx = res.find("\n**回答结束**")
    if end_idx != -1:
        res = res[:end_idx]
    return res


def _force_utf8_stdio() -> None:
    """Pin stdio to UTF-8 regardless of the host console code page."""
    sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def main() -> int:
    _force_utf8_stdio()
    payload = json.loads(sys.stdin.read())
    texts = [str(t) for t in payload.get("texts", [])]
    print(f"UIE_WORKER texts={len(texts)}", file=sys.stderr, flush=True)
    import paddle  # type: ignore[import-not-found]

    paddle.set_device("cpu")
    from paddlenlp.transformers import (  # type: ignore[import-not-found]
        AutoModelForCausalLM,
        AutoTokenizer,
    )

    model_dir = _resolve_model_dir()
    model = AutoModelForCausalLM.from_pretrained(model_dir, dtype="float32")
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(model_dir, padding_side="left")

    def infer(text: str, prompt: str) -> str:
        return _run_stage(text, prompt, model=model, tokenizer=tokenizer)

    bundle = build_documents(texts, infer=infer)
    sys.stdout.write(json.dumps(bundle, ensure_ascii=False))
    sys.stdout.flush()
    print("UIE_WORKER done", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
