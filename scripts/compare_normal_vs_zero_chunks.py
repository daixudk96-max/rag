"""对比分析：正常 chunk_id vs 全零 chunk_id 的节点特征。"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
results_file = REPO_ROOT / "verification" / "phase8-matched-validation-rerun" / "retrieval_results.json"
data = json.loads(results_file.read_text(encoding="utf-8"))

print("=== 对比分析：正常 chunk_id vs 全零 chunk_id ===")
print()

# 收集所有 Rank 1 的信息
normal_hits = []
zero_hits = []

for query_result in data["results"]:
    query_id = query_result["query_id"]
    rank1 = query_result["hits"][0] if query_result["hits"] else None

    if rank1:
        chunk_id = rank1.get("chunk_id", "")
        heading_path = rank1.get("heading_path", "")
        text_preview = rank1.get("text_preview", "")
        node_id = rank1.get("node_id", "")

        if chunk_id == "00000000-0000-0000-0000-000000000000":
            zero_hits.append({
                "query_id": query_id,
                "node_id": node_id,
                "heading_path": heading_path,
                "text_preview_len": len(text_preview),
                "text_preview": text_preview[:80],
            })
        else:
            normal_hits.append({
                "query_id": query_id,
                "node_id": node_id,
                "chunk_id": chunk_id,
                "heading_path": heading_path,
                "text_preview_len": len(text_preview),
                "text_preview": text_preview[:80],
            })

print("正常 chunk_id 的 Rank 1 hits (10 个):")
print()
for hit in normal_hits:
    print(f"  {hit['query_id']}:")
    print(f"    heading_path: {hit['heading_path']}")
    print(f"    text_preview 长度: {hit['text_preview_len']} 字符")
    print(f"    text_preview 预览: {hit['text_preview']}")
    print()

print("全零 chunk_id 的 Rank 1 hits (10 个):")
print()
for hit in zero_hits:
    print(f"  {hit['query_id']}:")
    print(f"    heading_path: {hit['heading_path']}")
    print(f"    text_preview 长度: {hit['text_preview_len']} 字符")
    print(f"    text_preview 预览: {hit['text_preview']}")
    print()

print("=== 关键对比 ===")
print()

# 统计 heading_path 层级
def count_heading_levels(heading_path):
    return len(heading_path.split("/"))

normal_avg_levels = sum(count_heading_levels(h["heading_path"]) for h in normal_hits) / len(normal_hits)
zero_avg_levels = sum(count_heading_levels(h["heading_path"]) for h in zero_hits) / len(zero_hits)

print(f"正常 chunk_id 平均 heading 层级: {normal_avg_levels:.1f}")
print(f"全零 chunk_id 平均 heading 层级: {zero_avg_levels:.1f}")
print()

# 统计 text_preview 长度
normal_avg_preview_len = sum(h["text_preview_len"] for h in normal_hits) / len(normal_hits)
zero_avg_preview_len = sum(h["text_preview_len"] for h in zero_hits) / len(zero_hits)

print(f"正常 chunk_id 平均 text_preview 长度: {normal_avg_preview_len:.0f} 字符")
print(f"全零 chunk_id 平均 text_preview 镀度: {zero_avg_preview_len:.0f} 字符")
print()

# 分析共同特征
print("正常 chunk_id 的 heading_path 共同特征:")
normal_paths = [h["heading_path"] for h in normal_hits]
for path in normal_paths:
    print(f"  - {path}")
print()

print("全零 chunk_id 的 heading_path 共同特征:")
zero_paths = [h["heading_path"] for h in zero_hits]
for path in zero_paths:
    print(f"  - {path}")
print()

print("=== 结论 ===")
print()
print("如果全零 chunk_id 的 heading_path 都是:")
print("  - root 节点（只有文档标题）")
print("  - heading 节点（只有章节标题，如 'PageIndex vs 当前实现对比'）")
print("说明这些节点没有被向量化，数据库里没有对应 chunks")
print()
print("如果正常 chunk_id 的 heading_path 包含:")
print("  - 实际内容节点（如 'Token消耗对比', '关键发现', '推荐集成方案'）")
print("说明这些节点被向量化了，数据库里有 chunks")
print()
print("这说明:")
print("  1. 数据库有 54 个 chunks（Phase 7 证据）")
print("  2. 但只覆盖了一部分节点")
print("  3. 检索流程偏向选 heading 节点，这些节点没有 chunks")
print("  4. 这是 '节点选择策略问题' + 'chunks 覆盖不全问题'，不是索引失败")