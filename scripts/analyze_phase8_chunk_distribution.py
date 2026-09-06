"""分析 Phase 8 检索结果的 chunk_id 分布。"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
results_file = REPO_ROOT / "verification" / "phase8-matched-validation-rerun" / "retrieval_results.json"
data = json.loads(results_file.read_text(encoding="utf-8"))

print("=== Phase 8 检索结果 chunk_id 分布分析 ===")
print()

total_hits = 0
normal_chunks = 0
zero_chunks = 0

# 按 query 分组统计
query_stats = []

for query_result in data["results"]:
    query_id = query_result["query_id"]
    query_text = query_result["query_text"]
    hits = query_result["hits"]

    query_normal = 0
    query_zero = 0
    query_total = len(hits)

    for hit in hits:
        total_hits += 1
        chunk_id = hit.get("chunk_id", "")

        if chunk_id == "00000000-0000-0000-0000-000000000000":
            zero_chunks += 1
            query_zero += 1
        else:
            normal_chunks += 1
            query_normal += 1

    query_stats.append({
        "query_id": query_id,
        "query_text": query_text[:50],
        "total": query_total,
        "normal": query_normal,
        "zero": query_zero,
        "normal_rate": query_normal / query_total if query_total > 0 else 0,
    })

print("总体统计:")
print(f"  总 hits: {total_hits}")
print(f"  正常 chunk_id: {normal_chunks} ({normal_chunks/total_hits:.1%})")
print(f"  全零 chunk_id: {zero_chunks} ({zero_chunks/total_hits:.1%})")
print()

print("按 Query 统计（正常 chunk_id 比例）:")
print()
for stat in query_stats:
    print(f"  {stat['query_id']}: 正常 {stat['normal']}/{stat['total']} ({stat['normal_rate']:.0%}) - {stat['query_text']}")
print()

# 分析 Rank 1 的 chunk_id
print("Rank 1 的 chunk_id 分析:")
print()
rank1_normal = 0
rank1_zero = 0

for query_result in data["results"]:
    query_id = query_result["query_id"]
    rank1 = query_result["hits"][0] if query_result["hits"] else None

    if rank1:
        chunk_id = rank1.get("chunk_id", "")
        if chunk_id == "00000000-0000-0000-0000-000000000000":
            rank1_zero += 1
            print(f"  {query_id} Rank 1: 全零 - {rank1['heading_path'][:40]} - preview: {rank1['text_preview'][:40]}")
        else:
            rank1_normal += 1
            print(f"  {query_id} Rank 1: 正常 ({chunk_id[:8]}...) - {rank1['heading_path'][:40]} - preview 长度: {len(rank1['text_preview'])} 字符")

print()
print(f"Rank 1 统计:")
print(f"  正常 chunk_id: {rank1_normal} ({rank1_normal/len(data['results']):.1%})")
print(f"  全零 chunk_id: {rank1_zero} ({rank1_zero/len(data['results']):.1%})")
print()

print("=== 分析结论 ===")
print()
print("如果大部分 Rank 1 的 chunk_id 是全零，说明：")
print("  1. 数据库有 spans/chunks（54 个）")
print("  2. 但检索流程没有找到这些 chunks")
print("  3. 这不是'数据库没数据'的问题，而是'检索流程没找到数据'的问题")
print()
print("如果大部分 Rank 1 的 chunk_id 是正常，说明：")
print("  1. 检索流程能找到 chunks")
print("  2. 但可能返回的内容不够准确")
print("  3. 这是内容质量问题，不是索引问题")