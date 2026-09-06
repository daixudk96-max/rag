# Phase 16-C1 中文实体抽取模型选型裁决（2026-07-13）

> **状态：技术基线已冻结，仍未授权执行。** 本文只固定模型 artifact、适配器契约与验收边界；不安装依赖、不下载权重、不改运行时代码、不执行 Phase 16。

## 1. 最终裁决

### 1.1 唯一主模型：ModelScope RaNER Chinese Large Generic

C1 首个必须交付的本地非生成式、固定标签中文 NER 模型固定为：

- 模型 ID：`iic/nlp_raner_named-entity-recognition_chinese-large-generic`
- 历史 README 别名：`damo/nlp_raner_named-entity-recognition_chinese-large-generic`
- 模型类型：XLM-RoBERTa Large + Transformer-CRF
- 任务：`named-entity-recognition`
- 模型仓库标注许可证：Apache License 2.0
- 仓库总大小：`2,262,195,577` bytes（约 2.11 GiB / 2.26 GB）
- 固定标签：`CORP`、`CW`、`GRP`、`LOC`、`PER`、`PROD`
- 首期运行开关：`RAG_ENTITY_EXTRACTOR=off|raner`，默认 `off`

这是**已经训练好的通用中文固定标签 NER checkpoint**。C1 初次使用不要求项目先做中文实体标注、微调或重新训练；项目小型人工标注集只用于验收和评测，不得成为让基线模型“能够工作”的隐藏前置条件。未来微调只能是 Phase 19 证据支持后的可选优化。

标准直接推理形态：

```python
from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks

ner_pipeline = pipeline(
    Tasks.named_entity_recognition,
    "iic/nlp_raner_named-entity-recognition_chinese-large-generic",
)

result = ner_pipeline(
    "他继续与貝塞斯達遊戲工作室在接下来辐射4游戏。"
)
```

官方模型卡示例输出：

```python
{
    "output": [
        {
            "type": "CORP",
            "start": 4,
            "end": 13,
            "span": "貝塞斯達遊戲工作室",
        },
        {
            "type": "CW",
            "start": 17,
            "end": 20,
            "span": "辐射4",
        },
    ]
}
```

该输出足以冻结 C1 mention adapter：

```python
mention_text = output["span"]
raw_label = output["type"]
char_start = output["start"]
char_end = output["end"]
confidence = None
confidence_kind = "unavailable"
```

标准 pipeline 输出没有 per-mention confidence。不得填常数或从 CRF 内部分数臆造“模型概率”。字符坐标必须在 adapter 中以原始规范化文本重新断言：

```python
span_text[char_start:char_end] == mention_text
```

### 1.2 为什么它符合“无需先标注训练的通用实体识别”

RaNER Large Generic 与 UIE 的类别不同：

- RaNER 是预训练完成的**固定标签 NER checkpoint**，输入原始中文文本即可直接产生预定义类型实体。
- UIE 是**schema-guided information extraction**，调用时需给出“人物、机构、地点”等 schema/prompt；它可以 zero-shot 工作，但不应被称为传统固定标签通用 NER。
- 项目不需要先标注和训练 RaNER；项目人工标注集承担的是独立验收，而不是模型启动条件。

官方模型卡报告的验证集结果为：

| 指标 | 数值 |
|---|---:|
| Precision | 91.55 |
| Recall | 91.33 |
| F1 | 91.44 |

按类型 F1：

| 标签 | F1 |
|---|---:|
| `CORP` | 89.30 |
| `CW` | 91.07 |
| `GRP` | 77.55 |
| `LOC` | 94.82 |
| `PER` | 96.92 |
| `PROD` | 87.29 |

这些数值只代表该模型卡声明的验证设置，不得与 MultiCoNER 2022 中文测试榜上的 DAMO 系统 macro-F1 或其他论文设置混为同一 checkpoint 的同一评测。

训练/评测语料来自中文 MultiCoNER 场景，确实包含中文 NER 标签，但其构建主要依赖 Wikipedia/Wikidata 映射、模板、槽位填充和机器翻译，并辅以人工 taxonomy 映射与样本质量检查。准确表述是半自动、远程/弱监督构造的中文 NER 数据，不应写成逐句完全人工 gold 标注。模型卡的 `169,361` 句声明与公开 split 数量口径存在差异，项目文档保留该差异，不自行拼接成新的数据集统计结论。

### 1.3 Artifact 冻结方式

ModelScope API 未提供可依赖的发布 tag，`master` 是可变引用。因此不能只记录模型 ID 或长期依赖在线 `master`；必须使用受控快照、逐文件 SHA-256 manifest、只读本地镜像和断网加载测试共同冻结。

主 artifact 文件：

| 文件 | 大小（bytes） | SHA-256 | ModelScope 文件来源 revision |
|---|---:|---|---|
| `pytorch_model.bin` | 2,239,833,895 | `62fbd5cae19c206d2219033f59b0bff9b9216c02471f8d4d96cd155a31e9412b` | `4d15e5b1427685cfd2cfc416903890219dc0582c` |
| `config.json` | 1,207 | `f8740e1a4b8ab43b2932023cb50cdb892084c640f9d80b915142093f3a986396` | `4d15e5b1427685cfd2cfc416903890219dc0582c` |
| `configuration.json` | 175 | `2757784508a1700160a96fdf187190a91bde1ee68dd1ed9b1ab70de0eb89a517` | `4d15e5b1427685cfd2cfc416903890219dc0582c` |
| `sentencepiece.bpe.model` | 5,069,051 | `cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865` | `4d15e5b1427685cfd2cfc416903890219dc0582c` |
| `tokenizer.json` | 17,082,661 | `984b1def3a3be6e7bcc33df5397c52fc77ed8ce49eaba7fc66cf623ae19aabf0` | `4d15e5b1427685cfd2cfc416903890219dc0582c` |
| `special_tokens_map.json` | 150 | `763f5bbbe86ef6d604ef28ad3647dc690d6d117c81c0d63e885416be8da1150` | `4d15e5b1427685cfd2cfc416903890219dc0582c` |
| `tokenizer_config.json` | 521 | `0525bc6493bb897fcd5b9fa2d4ca416c15bf61387c4e975018cde9998e1a5ed7` | `e260704d794924f4e4128402996bbb29cdfcbd91` |

Phase 16 受控 smoke test 必须解析并记录 SDK 实际取得的本地 snapshot revision；如果 SDK 不接受上述 commit 作为单一 revision，则以完整逐文件 SHA-256 manifest 作为最终完整性权威，不得伪称已有单一不可变 release tag。

### 1.4 标签到 OKF canonical type 的初始映射

| RaNER 标签 | 语义 | OKF canonical type 初始映射 |
|---|---|---|
| `PER` | 人物 | `Person` |
| `LOC` | 地点/设施 | `Location` |
| `CORP` | 公司/法人机构 | `Organization`（保留 `raw_label=CORP`） |
| `GRP` | 团体/其他组织 | `Organization`（保留 `raw_label=GRP`） |
| `CW` | 创意作品 | `CreativeWork` |
| `PROD` | 产品 | `Product` |

若 OKF 正式实体 schema 尚未包含 `CreativeWork` 或 `Product`，PLAN 必须先完成 schema 对齐；不得丢弃 `raw_label`，也不得把 `CW/PROD` 强行归为 Organization。`CORP` 与 `GRP` 即使暂时都映射到 `Organization`，原始细分类仍必须可追溯。

## 2. 备用与扩展模型

### 2.1 资源受限 fallback 候选：RaNER Chinese Base News

候选模型：

- 模型 ID：`iic/nlp_raner_named-entity-recognition_chinese-base-news`
- 历史别名：`damo/nlp_raner_named-entity-recognition_chinese-base-news`
- 架构：StructBERT + Transformer-CRF
- 固定标签：`PER`、`ORG`、`LOC`
- 训练域：MSRA 中文新闻
- 仓库大小：`409,491,567` bytes（约 390.5 MiB）
- 模型仓库标注许可证：Apache License 2.0
- 官方模型卡结果：Precision 96.41、Recall 96.98、F1 96.69（MSRA 新闻域）
- 标准输出：同样为 `type/start/end/span`，不要求项目先训练

主权重：

```text
pytorch_model.bin
size: 409203377
SHA-256: 0965359751fc889e03ae5a3295ffeecca54eca4b2b4a7d8432c50ee8971b275a
source revision: bf91e748219f3522a84cd128ea326509a4875825
```

它只是**资源受限降级候选**，不是与 Large Generic 等价的通用主模型：只有三类，且训练域是新闻。仅当 Phase 16 在目标 CPU/Windows 或 WSL 环境的基准证明 Large Generic 超出明确资源预算，并且项目人工集证明 Base News 的质量仍可接受时，才能通过单独记录的降级裁决采用。首期配置不得在未实现/未验收前公开 `base-news` 值。

### 2.2 可选领域 schema 扩展：PaddleNLP `uie-base`

UIE 不再是 C1 固定标签主基线。它保留为未来自定义领域类型、关系或 schema-guided 抽取的可选 adapter：

- `paddlenlp==2.8.1`
- 推理模型 ID：`uie-base`
- 资源族：`uie_base_v1.1`
- 普通文本 span 输出：`text/start/end/probability`
- 本地 extractive span inference，可 zero-shot 使用，不调用按 token 计费的生成式 LLM；论文使用 text-to-structure generation 表述不等于自回归文本生成，但它仍是 schema-guided IE，而不是固定标签 NER

保留它的原因是：输出字符 offset 和 probability 与 mention DTO 很匹配，并且 schema 可以覆盖 RaNER 固定六类之外的项目类型。但它依赖输入 schema，score 语义与 RaNER 不同，不能反过来强迫公共 `EntityExtractor.extract()` 接收 schema，也不能在 adapter 尚未实现和验收前加入首期 switch。未来如实现 UIE adapter，也必须把完整本地资源目录、Paddle/PaddleNLP 版本与 SHA-256 manifest 冻结后断网验收，不能把可变模型 ID 或首次联网缓存当作不可变 artifact。

### 2.3 研究/评测备用：HanLP MSRA NER

候选：HanLP `v2.1.1` 的 `hanlp.pretrained.ner.MSRA_NER_ELECTRA_SMALL_ZH`。

不作为 C1 主模型或部署 fallback，原因：

1. 标准高层输出是 `(entity_text, label, token_start, token_end)`，需要额外 token→character 对齐。
2. 标准输出没有 per-mention confidence。
3. 未找到官方 checkpoint checksum。
4. HanLP 源码是 Apache-2.0，但官方预训练模型默认许可为 CC BY-NC-SA 4.0，外部/商业用途不能安全假定。
5. 官方该 checkpoint 类型描述存在需要读取实际 label map 才能消除的歧义。

### 2.4 DeepKE 不冻结

DeepKE 是知识抽取框架，但当前没有同时满足以下条件的明确 C1 artifact：固定 checkpoint/revision、完整 checksum、稳定预测 DTO、该 checkpoint 的中文 benchmark、独立权重与数据许可。它不得成为 `RAG_ENTITY_EXTRACTOR` 已支持值，直到具体 artifact 通过同等级审查。

## 3. 冻结的适配器契约

### 3.1 公共 Protocol 与判别输入

固定标签基线不需要调用方传 schema。语料抽取与查询抽取复用同一个 adapter/label-map/output contract，但输入必须是显式判别联合，不能要求 query 伪造 corpus evidence：

```python
ExtractionInput = CorpusSpanInput | QueryTextInput

class EntityExtractor(Protocol):
    def extract(
        self,
        inputs: Sequence[ExtractionInput],
    ) -> list[MentionCandidate]: ...
```

两种输入共享 `input_id`、`input_kind`、不可变 `input_revision`、完整 `normalized_text`、`normalization_version` 和相同字符坐标语义：

- `CorpusSpanInput(input_kind="corpus_span")`：`input_id == span_id`，`input_revision == document_revision`，并强制携带不可变 `document_id/document_revision`、上游 document/span 坐标与可解析的 normalized→sidecar/raw evidence 投影；只有该变体的候选可映射并持久化到 `entity_mentions`、alias、merge-log 或 link。
- `QueryTextInput(input_kind="query_text")`：携带 immutable query-local `input_id/query_revision`，且 `input_revision == query_revision`；不要求也不得伪造 `document_id`、`document_revision`、`span_id` 或 sidecar 投影。其候选只用于当前 R3 seed normalization/recall；query 输入允许的候选来源只有 model/dictionary/rule，不能制造 `frontmatter` 来源。

抽取 DTO 的 `char_start/char_end` 唯一含义是：在对应输入的精确 `normalized_text` 上按 Python `str` Unicode code point 计数的零基、左闭右开 input-local 区间；它不是 UTF-8 byte offset、UTF-16 code-unit offset、grapheme-cluster offset、token index 或 document-global offset。抽取器不得改变文本后继续沿用旧坐标；如 NFKC、换行转换、空白折叠、删除、替换或重排会改变 code point 序列，normalizer 必须在模型调用前产生版本化映射。corpus 输入必须产生 evidence projection；query 输入只需保留 query-local mapping，不得在抽取后通过字符串搜索重建。

长文本分段是 adapter/runner 内部的版本化坐标层：每个 segment 必须带稳定 `segment_id`、parent `input_id`、parent-local `[segment_start, segment_end)` 与 `segmentation_version`。模型 segment-local offset 回写 parent input 后必须再次满足切片不变量。corpus mention 通过不可变 span/projection 计算 `document_char_start/document_char_end`；query mention 不产生 document 坐标。不得让同一 `char_start` 字段有时表示 input-local、有时表示 document-global。未来 UIE adapter 的 schema 由 adapter 构造配置持有，并带独立 `schema_version`；不得给所有 extractor 调用强加 UIE 专属参数。

### 3.2 `MentionCandidate`

```python
@dataclass(frozen=True)
class MentionCandidate:
    input_id: str
    input_kind: Literal["corpus_span", "query_text"]
    input_revision: str
    span_id: str | None
    mention_text: str
    raw_label: str
    entity_type: str
    char_start: int
    char_end: int
    confidence: float | None
    confidence_kind: Literal[
        "model_probability",
        "rule_weight",
        "dictionary_exact",
        "frontmatter_declared",
        "unavailable",
    ]
    source: Literal["model", "dictionary", "rule", "frontmatter"]
    extractor_id: str
    extractor_version: str
    model_id: str | None
    model_revision: str | None
    artifact_digest: str | None
    schema_version: str
    normalization_version: str
    segmentation_version: str
    label_map_digest: str
    runtime_compatibility_id: str
```

判别与持久化不变量：

```python
0 <= char_start < char_end <= len(input.normalized_text)
input.normalized_text[char_start:char_end] == mention_text

input_kind == "corpus_span"  => span_id is not None and input_id == span_id and input_revision == document_revision
input_kind == "query_text"   => span_id is None and input_revision == query_revision
```

只有 `corpus_span` candidate 可进入持久化 mention/alias/link 管线。`query_text` candidate、其 pre-merge audit 和 merger selected/suppressed/grouped artifact 全部是 request-scoped ephemeral data：不得写入任何 durable candidate audit、`entity_mentions`、`entity_merge_log`、alias、entity-link 或 corpus-evidence store；最多只能按查询隐私/保留策略输出有界、可脱敏的 observability metadata。任何 query artifact 进入上述 durable sink 都是契约错误。

RaNER adapter 规则：

- `type` → `raw_label`
- 版本化 label map → `entity_type`
- `span/start/end` → mention text 和字符坐标
- `confidence=None`
- `confidence_kind="unavailable"`
- `model_id="iic/nlp_raner_named-entity-recognition_chinese-large-generic"`
- `model_revision` 记录实际本地快照 revision；`artifact_digest` 指向完整 lock manifest digest
- 越界、空 span、切片不一致、未知 label 均拒绝输出并进入结构化错误统计；对 corpus 输入还必须保证零部分落库
- 不得用 `str.find`、substring search、返回文本首次出现位置或其他启发式手段恢复缺失/不一致坐标；重复实体文本会使这类恢复不确定
- `model_revision`、`artifact_digest`、逐文件 manifest、runtime compatibility ID、normalization/segmentation/label-map provenance 一经写入候选即不可由投影、合并或 canonical resolution 重写；替换 artifact 必须形成新的 provenance identity

模型概率、规则权重、词典 exact match 和 frontmatter 声明不是同一统计量。候选合并器不得未经校准直接比较不同 `confidence_kind` 的数值。NER 预测只能创建候选 mention，不能直接触发 canonical entity 永久合并。

所有有效原始候选（包含同源重复、嵌套和重叠）必须在合并前保留完整 pre-merge audit representation；独立、版本化合并器只能标记 selected/suppressed/grouped，不得删除原始边界和 provenance。对 corpus 输入，该审计可按持久化设计保留；对 query 输入，它只能存在于当前请求内，绝不进入 durable audit/merge/alias/link/evidence store。adapter 输出必须按稳定键排序（至少 `input_kind/input_id/input_revision/segment_id/char_start/char_end/raw_label/source identity`），不能依赖 backend 返回顺序。契约失败使用 typed per-input/per-segment error，至少记录 `input_kind/input_id/input_revision`、extractor/model revision、失败类别和原始字段摘要；单个输入内 fail-closed：corpus span 不产生部分 mention/alias/merge-log/link 写入，query input 不产生部分 R3 seeds；其他输入可按确定性策略继续并形成显式 batch failure report。

## 4. Phase 16 验收新增硬门

1. `RAG_ENTITY_EXTRACTOR` 首期支持值只允许 `off|raner`，默认 `off`；未实现的 UIE、Base News、HanLP、DeepKE 值不得提前暴露。
2. Large Generic 必须不经项目微调直接完成真实中文推理；只交付 Protocol、mock 或纯词典实现不能关闭 C1。
3. 使用不在领域词典中的人物、组织、地点，以及至少一个 `CW` 或 `PROD` fixture，验证固定标签发现、映射和 `[start,end)` offset round-trip；坐标 fixture 必须覆盖中文全角标点、重复实体文本、换行/空白、combining mark 和 astral-plane emoji，证明 DTO 使用 Python Unicode code-point 而非 byte/UTF-16/token offset。
4. 项目建立小型中文人工标注验收集，报告 precision/recall/F1、按类型 recall、offset exact match、unknown-label/error 数量。该集合只用于验收，不是初始训练前置。
5. 长文本必须在规范化文本上确定性分段；每段带稳定 segment identity、parent interval 与 segmentation version，分段局部 offset 回写 span-local/document projection 后仍满足切片不变量。模型卡上限 512 tokens 不得被当作任意长输入保证。
6. 完整逐文件 SHA-256 manifest、只读本地镜像、断网冷启动和重复加载必须通过；运行时不得依赖首次联网下载。
7. 在目标 Windows 11 CPU 和候选 WSL 环境记录冷启动时间、吞吐、p50/p95 span latency、峰值 RAM、磁盘占用和失败恢复。官方没有提供该 2.26 GB 模型的 CPU latency/RAM 数据，因此不得在实测前宣称部署成本可接受。
8. 若 Large Generic 超预算，只能形成显式降级报告，比较 Base News 在同一项目人工集上的质量损失后再裁决；不得静默替换。
9. 运行时以 fake/spy client 断言零生成式 LLM 调用。
10. 所有 NER 候选保留模型、revision、artifact、label-map、offset 和来源 provenance；不得直接永久合并实体。
11. ModelScope/AdaSeq/PyTorch/Python 的精确兼容 tuple 需在隔离环境 smoke test 后冻结。已知文档信号包括 AdaSeq 对 ModelScope `1.9.5` 的兼容说明，但在 Windows/WSL 离线实测前不把它写成已验证生产 tuple。
12. Phase 20 G6 前必须复核仓库代码、模型权重、底座模型与训练数据许可；模型卡的 Apache-2.0 标记不能替代完整资产链法务审查。
13. 重复文本/重叠候选 fixture 必须证明 adapter 不以 `str.find` 猜坐标、pre-merge 原始候选不丢失、稳定排序与版本化 merger 在重跑时输出一致。
14. partial-batch fixture 必须证明一个 corpus span 的 schema/offset/projection 失败会生成 typed failure、该 span 零部分写入、其余 input 按固定策略继续；重试后持久化幂等且 provenance 不被重写。
15. query fixture 必须证明 `input_revision == query_revision`、query candidates/audit/merger artifacts 只在 request scope 内存在，且所有 durable candidate audit、`entity_mentions`、`entity_merge_log`、alias、link 与 corpus-evidence sinks 均为零写入。

## 5. 与 C2 的边界

本裁决只覆盖 C1 mention discovery。C2 中文局部指代链仍是条件性、默认关闭的独立 wave：

- RaNER 不等于 coreference resolver。
- C1 不因选择 RaNER 而授权 `relation_mentions`。
- C2 不得永久合并 canonical entity。
- C2 的功能就绪门在 Phase 16，净收益/default-on 裁决仍归 Phase 19 G3。

## 6. 主要来源

- [ModelScope RaNER Chinese Large Generic 模型页](https://modelscope.cn/models/iic/nlp_raner_named-entity-recognition_chinese-large-generic)
- [ModelScope RaNER Chinese Large Generic 仓库 API](https://modelscope.cn/api/v1/models/iic/nlp_raner_named-entity-recognition_chinese-large-generic)
- [ModelScope RaNER Chinese Base News 模型页](https://modelscope.cn/models/iic/nlp_raner_named-entity-recognition_chinese-base-news)
- [ModelScope AdaSeq 官方仓库](https://github.com/modelscope/AdaSeq)
- [MultiCoNER 2022 shared task paper](https://aclanthology.org/2022.semeval-1.196/)
- [PaddleNLP v2.8.1 `information_extraction.py`](https://raw.githubusercontent.com/PaddlePaddle/PaddleNLP/v2.8.1/paddlenlp/taskflow/information_extraction.py)
- [PaddleNLP Taskflow UIE 文档](https://paddlenlp.readthedocs.io/en/stable/model_zoo/taskflow.html)
- [HanLP 中文 NER 模型目录](https://hanlp.hankcs.com/docs/api/hanlp/pretrained/ner.html)
- [HanLP 仓库及模型许可说明](https://github.com/hankcs/HanLP)
- [DeepKE 官方仓库](https://github.com/zjunlp/DeepKE)
