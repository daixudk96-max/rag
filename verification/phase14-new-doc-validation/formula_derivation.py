#!/usr/bin/env python3
"""Derive the correct hotspot scoring formula"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print('='*80)
print('热点评分公式推导：从语义到数学')
print('='*80)

print('\n热点的本质定义:')
print('  "热点" = 高质量子节点 + 高覆盖率')
print('  - 高质量：dual_hot子节点的平均相似度高')
print('  - 高覆盖率：dual_hot子节点占比大')
print('  - 缺一不可：低质量全覆盖、高质量低覆盖都不是热点')

print('\n' + '='*80)
print('三种候选公式对比')
print('='*80)

scenarios = [
    {
        'name': 'Phase 14',
        'parents': [
            {'name': 'Parent A', 'total': 2, 'dual_hot': 2, 'avg_hot_sim': 0.53},
            {'name': 'Parent B', 'total': 7, 'dual_hot': 5, 'avg_hot_sim': 0.57},
        ]
    },
    {
        'name': '极端例子',
        'parents': [
            {'name': 'Parent C', 'total': 100, 'dual_hot': 5, 'avg_hot_sim': 0.80},
            {'name': 'Parent D', 'total': 10, 'dual_hot': 3, 'avg_hot_sim': 0.60},
        ]
    },
    {
        'name': '高质量低覆盖',
        'parents': [
            {'name': 'Parent E', 'total': 50, 'dual_hot': 10, 'avg_hot_sim': 0.90},
            {'name': 'Parent F', 'total': 20, 'dual_hot': 8, 'avg_hot_sim': 0.70},
        ]
    },
]

def formula1_simple_avg(parent, penalty=0.0):
    """方案1：简单平均（用户建议）"""
    hot_score = parent['dual_hot'] * parent['avg_hot_sim']
    penalty_score = (parent['total'] - parent['dual_hot']) * penalty
    total = hot_score + penalty_score
    avg = total / parent['total']
    return avg

def formula2_weighted_quality(parent):
    """方案2：加权质量（质量 × 覆盖率）"""
    coverage = parent['dual_hot'] / parent['total']
    quality = parent['avg_hot_sim']
    score = quality * coverage
    return score

def formula3_hybrid(parent, coverage_weight=0.3, quality_weight=0.7):
    """方案3：混合评分（覆盖率权重 + 质量权重）"""
    coverage = parent['dual_hot'] / parent['total']
    quality = parent['avg_hot_sim']
    score = coverage * coverage_weight + quality * quality_weight
    return score

print('\n方案1：简单平均（penalty=0）')
print('-'*80)

for scenario in scenarios:
    print(f'\n{scenario["name"]}:')

    scores = []
    for parent in scenario['parents']:
        avg = formula1_simple_avg(parent, penalty=0.0)
        scores.append(avg)
        print(f'  {parent["name"]}: avg={avg:.4f}')

    winner = scenario['parents'][scores.index(max(scores))]
    max_dual_hot = max(p['dual_hot'] for p in scenario['parents'])

    if winner['dual_hot'] == max_dual_hot:
        print(f'  ✓ 选择 {winner["name"]} (dual_hot={winner["dual_hot"]})')
    else:
        print(f'  ✗ 选择 {winner["name"]} (dual_hot={winner["dual_hot"]} vs max={max_dual_hot})')

print('\n' + '='*80)
print('方案2：加权质量（quality × coverage）')
print('='*80)
print('\n公式: avg_hot_similarity * (dual_hot / total)')
print('语义: 高质量 × 高覆盖率 → 真正热点')

for scenario in scenarios:
    print(f'\n{scenario["name"]}:')

    scores = []
    for parent in scenario['parents']:
        score = formula2_weighted_quality(parent)
        scores.append(score)
        coverage = parent['dual_hot'] / parent['total']
        print(f'  {parent["name"]}: {parent["avg_hot_sim"]:.2f} * {coverage:.2f} = {score:.4f}')

    winner = scenario['parents'][scores.index(max(scores))]
    max_dual_hot = max(p['dual_hot'] for p in scenario['parents'])

    if winner['dual_hot'] == max_dual_hot:
        print(f'  ✓ 选择 {winner["name"]} (dual_hot={winner["dual_hot"]})')
    else:
        print(f'  ✗ 选择 {winner["name"]} (dual_hot={winner["dual_hot"]} vs max={max_dual_hot})')

print('\n' + '='*80)
print('方案3：混合评分（coverage_weight + quality_weight）')
print('='*80)

print('\n配置: coverage_weight=0.3, quality_weight=0.7')
print('语义: 覆盖率30% + 质量70%（质量更重要）')

for scenario in scenarios:
    print(f'\n{scenario["name"]}:')

    scores = []
    for parent in scenario['parents']:
        score = formula3_hybrid(parent, coverage_weight=0.3, quality_weight=0.7)
        scores.append(score)
        coverage = parent['dual_hot'] / parent['total']
        print(f'  {parent["name"]}: {coverage:.2f}*0.3 + {parent["avg_hot_sim"]:.2f}*0.7 = {score:.4f}')

    winner = scenario['parents'][scores.index(max(scores))]
    max_dual_hot = max(p['dual_hot'] for p in scenario['parents'])

    if winner['dual_hot'] == max_dual_hot:
        print(f'  ✓ 选择 {winner["name"]} (dual_hot={winner["dual_hot"]})')
    else:
        print(f'  ✗ 选择 {winner["name"]} (dual_hot={winner["dual_hot"]} vs max={max_dual_hot})')

print('\n' + '='*80)
print('总结对比')
print('='*80)

# Calculate accuracy for each formula
def test_accuracy(formula_func, scenarios):
    correct = 0
    for scenario in scenarios:
        scores = [formula_func(p) for p in scenario['parents']]
        winner = scenario['parents'][scores.index(max(scores))]
        max_dual_hot = max(p['dual_hot'] for p in scenario['parents'])
        if winner['dual_hot'] == max_dual_hot:
            correct += 1
    return correct / len(scenarios)

acc1 = test_accuracy(lambda p: formula1_simple_avg(p, penalty=0.0), scenarios)
acc2 = test_accuracy(formula2_weighted_quality, scenarios)
acc3 = test_accuracy(lambda p: formula3_hybrid(p, coverage_weight=0.3, quality_weight=0.7), scenarios)

print('\n准确率对比:')
print(f'  方案1（简单平均）: {acc1:.1%}')
print(f'  方案2（加权质量）: {acc2:.1%}')
print(f'  方案3（混合评分）: {acc3:.1%}')

print('\n' + '='*80)
print('关键发现')
print('='*80)

print('\n1. 简单平均（用户建议）在Phase 14失败:')
print('   - Parent A (2/2全覆盖): avg=0.53, 被选中 ✗')
print('   - Parent B (5/7部分覆盖): avg=0.41, 未选中 ✗')
print('   - 原因：Parent A虽然质量低，但无无关子节点')
print('   - Parent B虽然有高质量子节点，但2个无关子节点拉低平均')

print('\n2. 加权质量（质量×覆盖率）完美解决所有场景:')
print('   - Phase 14: Parent B (0.57*0.71=0.40) > Parent A (0.53*1.0=0.53) ✗')
print('     等等，计算错了！')
print('     - Parent A: 0.53 * 1.00 = 0.53')
print('     - Parent B: 0.57 * 0.71 = 0.40')
print('     - Parent A > Parent B，仍然错误！✗')

print('\n   这说明：')
print('   - 简单乘法仍然偏向"全覆盖"父节点')
print('   - 需要更精细的权重分配')

print('\n3. 混合评分（coverage_weight + quality_weight）:')
print('   - 需要调整权重来平衡"覆盖率"和"质量"')
print('   - 如果quality_weight > coverage_weight:')
print('     - Parent A: 1.0*0.3 + 0.53*0.7 = 0.671')
print('     - Parent B: 0.71*0.3 + 0.57*0.7 = 0.60')
print('     - Parent A仍然胜出！✗')

print('\n' + '='*80)
print('根本矛盾')
print('='*80)

print('\n核心矛盾：')
print('  Parent A: 覆盖率完美（1.0）但质量低（0.53）')
print('  Parent B: 覆盖率中等（0.71）但质量高（0.57）')

print('\n任何公式都需要权衡：')
print('  - 重视覆盖率 → 选择Parent A ✗')
print('  - 重视质量 → 但Parent A覆盖率完美，很难超越')

print('\n唯一解决方案：')
print('  引入"子节点数量"作为独立因素')
print('  Parent B有5个dual_hot vs Parent A只有2个')
print('  数量优势应该体现在评分中')