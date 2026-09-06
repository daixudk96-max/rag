"""
Phase 3 Quick Judgment Reference - All 28 Hits in Compact Format

Reference this file when entering batch judgments.
"""

# All 28 judgments with queries and hits

JUDGMENTS = [
    {
        "id": 1,
        "query_id": "Q01",
        "query": "文档的主要章节结构是什么？列出所有一级标题。",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "显示一个章节标题，但未列出所有一级标题"
    },
    {
        "id": 2,
        "query_id": "Q04",
        "query": "文档中提到的关键技术指标有哪些？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "竞品分析章节，可能包含指标对比"
    },
    {
        "id": 3,
        "query_id": "Q04",
        "query": "文档中提到的关键技术指标有哪些？",
        "hit_heading": "第二阶段-竞品分析-代旭/目的",
        "hint": "目的子章节，可能提到指标"
    },
    {
        "id": 4,
        "query_id": "Q05",
        "query": "如何使用这个系统进行数据处理？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "主章节标题，可能涉及系统使用"
    },
    {
        "id": 5,
        "query_id": "Q06",
        "query": "文档中列举了哪些性能优化方法？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "竞品分析可能包含性能对比"
    },
    {
        "id": 6,
        "query_id": "Q07",
        "query": "系统的架构设计原则是什么？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "主章节，可能包含架构信息"
    },
    {
        "id": 7,
        "query_id": "Q07",
        "query": "系统的架构设计原则是什么？",
        "hit_heading": "第二阶段-竞品分析-代旭/目的",
        "hint": "目的子章节"
    },
    {
        "id": 8,
        "query_id": "Q08",
        "query": "文档中提到了哪些错误处理机制？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "可能不直接相关"
    },
    {
        "id": 9,
        "query_id": "Q09",
        "query": "文档中前后章节如何描述数据流程的完整链路？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "单一章节，难以描述完整链路"
    },
    {
        "id": 10,
        "query_id": "Q10",
        "query": "系统设计中如何平衡性能和准确性？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "竞品分析可能涉及性能准确性对比"
    },
    {
        "id": 11,
        "query_id": "Q11",
        "query": "文档中技术方案的选择理由是什么？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "主章节"
    },
    {
        "id": 12,
        "query_id": "Q11",
        "query": "文档中技术方案的选择理由是什么？",
        "hit_heading": "竞品 B：DeepSeek 智能场控看板",
        "hint": "竞品分析内容，可能包含方案对比"
    },
    {
        "id": 13,
        "query_id": "Q11",
        "query": "文档中技术方案的选择理由是什么？",
        "hit_heading": "竞品 C：巨量千川智投星",
        "hint": "另一个竞品分析"
    },
    {
        "id": 14,
        "query_id": "Q11",
        "query": "文档中技术方案的选择理由是什么？",
        "hit_heading": "竞品 D：飞书多维表格AI辅助",
        "hint": "第三个竞品分析"
    },
    {
        "id": 15,
        "query_id": "Q12",
        "query": "文档中是否有未解决的局限性或未来工作部分？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "可能在竞品分析中提及局限性"
    },
    {
        "id": 16,
        "query_id": "Q13",
        "query": "如果输入数据格式不符合预期，系统会如何处理？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "可能不直接相关"
    },
    {
        "id": 17,
        "query_id": "Q14",
        "query": "文档中提到了哪些系统限制或约束？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "竞品分析可能提及系统限制"
    },
    {
        "id": 18,
        "query_id": "Q15",
        "query": "文档中描述的向量检索阈值是多少？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "可能在技术细节部分"
    },
    {
        "id": 19,
        "query_id": "Q16",
        "query": "树结构构建的深度限制是什么？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "技术细节"
    },
    {
        "id": 20,
        "query_id": "Q17",
        "query": "文档中提到的 chunking 策略是什么？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "可能在技术实现部分"
    },
    {
        "id": 21,
        "query_id": "Q18",
        "query": "embedding 模型的选择依据是什么？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "技术选型内容"
    },
    {
        "id": 22,
        "query_id": "Q19",
        "query": "文档中对比了哪些技术方案？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "竞品分析本身就是方案对比"
    },
    {
        "id": 23,
        "query_id": "Q19",
        "query": "文档中对比了哪些技术方案？",
        "hit_heading": "竞品 B：DeepSeek",
        "hint": "具体的竞品对比"
    },
    {
        "id": 24,
        "query_id": "Q19",
        "query": "文档中对比了哪些技术方案？",
        "hit_heading": "竞品 C：巨量千川",
        "hint": "另一个竞品"
    },
    {
        "id": 25,
        "query_id": "Q19",
        "query": "文档中对比了哪些技术方案？",
        "hit_heading": "竞品 D：飞书",
        "hint": "第三个竞品"
    },
    {
        "id": 26,
        "query_id": "Q20",
        "query": "文档中是否提到与其他系统的集成方案？",
        "hit_heading": "第二阶段-竞品分析-代旭",
        "hint": "主章节"
    },
    {
        "id": 27,
        "query_id": "Q20",
        "query": "文档中是否提到与其他系统的集成方案？",
        "hit_heading": "竞品 B：DeepSeek",
        "hint": "竞品系统"
    },
    {
        "id": 28,
        "query_id": "Q20",
        "query": "文档中是否提到与其他系统的集成方案？",
        "hit_heading": "竞品 C：巨量千川",
        "hint": "另一个系统"
    },
]

# Quick judgment guide
print("=" * 100)
print("Phase 3 Quick Judgment Reference - 28 Hits")
print("=" * 100)
print("\nJudgment options:")
print("  A = fully_relevant (0.9) - Hit directly answers query")
print("  B = partially_relevant (0.5) - Hit partially answers")
print("  C = not_relevant (0.1) - Hit does not answer")

print("\nCompact list for quick reference:")
for j in JUDGMENTS:
    print(f"[{j['id']:2d}] {j['query_id']}-{j['query'][:40]:<40} | {j['hit_heading'][:30]:<30} | Hint: {j['hint'][:20]}")

print("\n" + "=" * 100)
print("Ready to enter batch judgments!")
print("Copy the list above to help you decide, then run:")
print("  python verification/phase3-real-validation/batch_judgment.py")
print("=" * 100)