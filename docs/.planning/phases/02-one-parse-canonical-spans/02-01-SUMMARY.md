# Phase 2 Summary — One Parse -> Canonical Spans

## Status
DONE

## What shipped
- `src/parser/docling_wrapper.py`：Docling wrapper + contract enforcement
- `src/parser/normalization.py`：文本与标题最小标准化函数
- `src/parser/span_generator.py`：从一次解析输出派生 canonical spans
- `src/parser/__init__.py`：parser package 导出
- `tests/fixtures/sample_minimal.pdf`：最小 PDF fixture
- `tests/test_docling_wrapper.py`：wrapper contract / metadata / determinism 测试
- `tests/test_span_generation.py`：span generation / persistence 测试
- `tests/test_phase2_e2e.py`：PDF -> Docling -> spans -> PostgreSQL 端到端测试

## Verification evidence
- Phase 2 tests: `9 passed`
- Phase 1 schema tests: `7 passed`
- Phase 1 CRUD tests: `9 passed`
- PostgreSQL 容器 healthy

## Key verified truths
1. 原文可以通过 Docling 只解析一次
2. Wrapper 能强制 `parser_name == Docling`
3. 相同 contract + 相同 PDF 下解析输出稳定
4. 解析输出包含 page_no / heading_path / text / offsets
5. 可以从解析输出稳定生成 canonical spans
6. spans 可以写入 PostgreSQL `canonical_spans`
7. 端到端流程：PDF -> Docling -> spans -> PostgreSQL 已跑通

## Notes / caveats
- 当前 sample PDF 极小，验证的是机制，不是复杂文档结构覆盖度
- heading_path 现在是最小可行规则，复杂多级标题与目录场景需后续增强
- offset 目前基于 `normalized_char_offset` 的本地生成逻辑，后续要和更复杂 normalization contract 一起演进
- Docling 运行时会触发 OCR/torch 相关 warning，但不阻断结果

## Next best step
进入 Phase 3：Keyword Path，先把 `PM2.5`、标准号、节目名等精确术语检索在 PostgreSQL 主干上跑通，并保持结果可回 `span_id / page_no / heading_path`。