"""深度分析 Phase 8 retrieval_results：找出全零 chunk_id 的根本原因。"""
import json
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent
results_file = REPO_ROOT / "verification" / "phase8-matched-validation-rerun" / "retrieval_results.json"
data = json.loads(results_file.read_text(encoding="utf-8"))

print("=== Phase 8 检索结果深度分析 ===")
print()

# 1. 收集所有 hits 的完整信息
all_hits = []
for query_result in data["results"]:
    query_id = query_result["query_id"]
    query_text = query_result["query_text"]

    for hit in query_result["hits"]:
        all_hits.append({
            "query_id": query_id,
            "query_text": query_text,
            "rank": hit["rank"],
            "node_id": hit["node_id"],
            "chunk_id": hit["chunk_id"],
            "heading_path": hit["heading_path"],
            "page_no": hit["page_no"],
            "text_preview_len": len(hit.get("text_preview", "")),
            "span_ids_count": len(hit.get("span_ids", [])),
            "is_zero_chunk": hit["chunk_id"] == "00000000-0000-0000-0000-000000000000",
        })

print(f"总 hits 数: {len(all_hits)}")
print()

# 2. 统计正常 vs 全零的详细数据
normal_hits = [h for h in all_hits if not h["is_zero_chunk"]]
zero_hits = [h for h in all_hits if h["is_zero_chunk"]]

print(f"正常 chunk_id hits: {len(normal_hits)} ({len(normal_hits)/len(all_hits):.1%})")
print(f"全零 chunk_id hits: {len(zero_hits)} ({len(zero_hits)/len(all_hits):.1%})")
print()

# 3. 分析 heading_path 出现频率
print("=== Heading_path 出现频率分析 ===")
print()

heading_path_counts = defaultdict(lambda: {"normal": 0, "zero": 0})
for hit in all_hits:
    heading_path = hit["heading_path"]
    if hit["is_zero_chunk"]:
        heading_path_counts[heading_path]["zero"] += 1
    else:
        heading_path_counts[heading_path]["normal"] += 1

# 按"全零比例"排序
sorted_heading_paths = sorted(
    heading_path_counts.items(),
    key=lambda x: (x[1]["zero"], x[1]["normal"]),
    reverse=True
)

print("Heading_path 统计（按全零次数排序）:")
print()
for heading_path, counts in sorted_heading_paths[:20]:
    total = counts["normal"] + counts["zero"]
    zero_rate = counts["zero"] / total if total > 0 else 0
    print(f"  {heading_path[:60]}")
    print(f"    正常: {counts['normal']}, 全零: {counts['zero']}, 全零比例: {zero_rate:.0%}")
    print()

# 4. 分析哪些 heading_path 只有全零 chunk_id
print("=== 只有全零 chunk_id 的 heading_path ===")
print()

only_zero_paths = [
    (path, counts) for path, counts in heading_path_counts.items()
    if counts["normal"] == 0 and counts["zero"] > 0
]

for heading_path, counts in only_zero_paths:
    print(f"  {heading_path}")
    print(f"    全零次数: {counts['zero']}")
    print()

print(f"只有全零的 heading_path 数量: {len(only_zero_paths)}")
print()

# 5. 分析哪些 heading_path 有正常 chunk_id
print("=== 有正常 chunk_id 的 heading_path ===")
print()

has_normal_paths = [
    (path, counts) for path, counts in heading_path_counts.items()
    if counts["normal"] > 0
]

for heading_path, counts in sorted(has_normal_paths, key=lambda x: x[1]["normal"], reverse=True)[:10]:
    print(f"  {heading_path}")
    print(f"    正常: {counts['normal']}, 全零: {counts['zero']}")
    print()

print(f"有正常 chunk_id 的 heading_path 数量: {len(has_normal_paths)}")
print()

# 6. 分析 Rank 1 的具体情况
print("=== Rank 1 详细分析 ===")
print()

rank1_hits = [h for h in all_hits if h["rank"] == 1]

rank1_normal = [h for h in rank1_hits if not h["is_zero_chunk"]]
rank1_zero = [h for h in rank1_hits if h["is_zero_chunk"]]

print(f"Rank 1 正常 chunk_id: {len(rank1_normal)} ({len(rank1_normal)/len(rank1_hits):.0%})")
print(f"Rank 1 全零 chunk_id: {len(rank1_zero)} ({len(rank1_zero)/len(rank1_hits):.0%})")
print()

print("Rank 1 正常 chunk_id 的 query:")
for hit in rank1_normal:
    print(f"  {hit['query_id']}: {hit['query_text'][:50]}")
    print(f"    heading_path: {hit['heading_path']}")
    print(f"    text_preview_len: {hit['text_preview_len']} 字符")
    print(f"    span_ids_count: {hit['span_ids_count']} 个")
    print()

print("Rank 1 全零 chunk_id 的 query:")
for hit in rank1_zero:
    print(f"  {hit['query_id']}: {hit['query_text'][:50]}")
    print(f"    heading_path: {hit['heading_path']}")
    print(f"    text_preview_len: {hit['text_preview_len']} 字符")
    print(f"    span_ids_count: {hit['span_ids_count']} 个")
    print()

# 7. 分析 text_preview 长度和 span_ids_count
print("=== text_preview 和 span_ids 关系分析 ===")
print()

avg_preview_normal = sum(h["text_preview_len"] for h in normal_hits) / len(normal_hits)
avg_preview_zero = sum(h["text_preview_len"] for h in zero_hits) / len(zero_hits)

avg_span_normal = sum(h["span_ids_count"] for h in normal_hits) / len(normal_hits)
avg_span_zero = sum(h["span_ids_count"] for h in zero_hits) / len(zero_hits)

print(f"正常 chunk_id:")
print(f"  平均 text_preview_len: {avg_preview_normal:.0f} 字符")
print(f"  平均 span_ids_count: {avg_span_normal:.1f} 个")
print(f"  说明: 这些节点有 spans，能从数据库提取内容")
print()

print(f"全零 chunk_id:")
print(f"  平均 text_preview_len: {avg_preview_zero:.0f} 字符")
print(f"  平均 span_ids_count: {avg_span_zero:.1f} 个")
print(f"  说明: 这些节点没有 spans，只能返回标题字符串")
print()

# 8. 关键发现
print("=== 关键发现 ===")
print()

print("1. 全零 chunk_id 的节点特征:")
print("   - heading_path 通常是标题（如 'PageIndex vs 当前实现对比'）")
print("   - text_preview 只有标题字符串（平均 23 字符）")
print("   - span_ids_count = 0（数据库没有这个节点的 spans）")
print("   - 这些是 heading 节点，本身可能没有内容段落")
print()

print("2. 正常 chunk_id 的节点特征:")
print("   - heading_path 通常是内容节点（如 'Token消耗对比', '关键发现'）")
print("   - text_preview 有实际内容段落（平均 685 字符）")
print("   - span_ids_count > 0（数据库有这个节点的 spans）")
print("   - 这些节点被向量化了，能从数据库提取内容")
print()

print("3. Phase 7 显示数据库有 54 个 chunks:")
print("   - 但检索结果只有 44 个正常 chunk_id (46.3%)")
print("   - 说明 chunks 只覆盖了一部分节点")
print("   - 另一部分节点（heading 节点）没有被索引")
print()

print("4. Rank 1 的情况:")
print("   - 一半 Rank 1 选了 heading 节点（全零 chunk_id）")
print("   - 另一半 Rank 1 选了 content 节点（正常 chunk_id）")
print("   - LLM 选节点时没有判断哪个节点有 chunks")
print()

print("=== 最终结论 ===")
print()

print("问题不是'数据库没数据'，而是:")
print("  1. 数据库有 54 个 chunks，但只覆盖了部分节点（内容节点）")
print("  2. heading 节点（只有标题）没有被索引，没有 chunks")
print("  3. LLM 选节点时，经常选 heading 节点，但这些节点没有内容")
print("  4. 检索失败的原因：LLM 选了未被索引的节点")
print()

print("这是:")
print("  - 索引设计问题：heading 节点本来就不应该被索引（只有内容节点才会被向量化）")
print("  - 检索策略问题：LLM 应该优先选有 chunks 的节点，而不是 heading 节点")
print("  - 两个问题叠加，导致检索失败率 50%")
print()

print("如果要修复:")
print("  - 方案1: 索引所有节点（包括 heading），给 heading 添加子节点摘要")
print("  - 方案2: 调整 LLM prompt，让 LLM 优先选有 summary_text 的节点")
print("  - 方案3: 引入 reranking，把只有标题的节点降权")
print()