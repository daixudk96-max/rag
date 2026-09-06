#!/usr/bin/env python3
"""过拟合风险分析：不同文档结构下的权重调整效果"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print('='*80)
print('过拟合风险评估：权重调整是否只对 Phase 14 有效？')
print('='*80)

# 定义三种文档结构场景
scenarios = [
    {
        'name': 'Phase 14 文档（当前）',
        'parents': [
            {'name': 'Parent A（低相关）', 'children': 2, 'dual_hot': 2, 'avg_vector': 0.53},
            {'name': 'Parent B（高相关）', 'children': 7, 'dual_hot': 5, 'avg_vector': 0.57},
        ]
    },
    {
        'name': '大文档（更多子节点）',
        'parents': [
            {'name': 'Parent C', 'children': 15, 'dual_hot': 10, 'avg_vector': 0.60},
            {'name': 'Parent D', 'children': 10, 'dual_hot': 8, 'avg_vector': 0.55},
        ]
    },
    {
        'name': '扁平文档（父节点少）',
        'parents': [
            {'name': 'Parent E', 'children': 3, 'dual_hot': 3, 'avg_vector': 0.70},
            {'name': 'Parent F', 'children': 5, 'dual_hot': 4, 'avg_vector': 0.65},
        ]
    }
]

def calculate_score(parent, coverage_weight=0.40, support_weight=0.30, cap=5.0):
    """计算父节点评分"""
    coverage_ratio = parent['dual_hot'] / parent['children']
    avg_child_vector = parent['avg_vector']
    support_bonus = min(parent['dual_hot'] / cap, 1.0) if cap != float('inf') else parent['dual_hot'] / 5.0

    score = (
        coverage_ratio * coverage_weight +
        avg_child_vector * 0.30 +
        support_bonus * support_weight
    )

    return score, coverage_ratio, support_bonus

print('\n当前调整效果验证（cap=5.0, coverage_weight=0.40, support_weight=0.30）')
print('-'*80)

for scenario in scenarios:
    print(f'\n{scenario["name"]}:')

    scores = []
    for parent in scenario['parents']:
        score, coverage_ratio, support_bonus = calculate_score(parent, cap=5.0)
        scores.append(score)

        print(f'  {parent["name"]}:')
        print(f'    children={parent["children"]}, dual_hot={parent["dual_hot"]}')
        print(f'    coverage_ratio={coverage_ratio:.2f}, support_bonus={support_bonus:.2f}')
        print(f'    score={score:.4f}')

    # 判断选择结果是否合理
    winner_idx = scores.index(max(scores))
    winner = scenario['parents'][winner_idx]

    # 检查是否选择了 dual_hot 最多的父节点
    max_dual_hot = max(p['dual_hot'] for p in scenario['parents'])
    if winner['dual_hot'] == max_dual_hot:
        print(f'  ✓ 选择 dual_hot 最多父节点（{winner["name"]}）')
    else:
        print(f'  ✗ 未选择 dual_hot 最多父节点（{winner["name"]}，dual_hot={winner["dual_hot"]} vs max={max_dual_hot}）')

print('\n' + '='*80)
print('方案对比：调整封顶阈值的影响')
print('='*80)

caps_to_test = [5.0, 8.0, 10.0, float('inf')]

for cap in caps_to_test:
    cap_label = f'{int(cap)}' if cap != float('inf') else '无封顶'
    print(f'\n封顶阈值 = {cap_label}')
    print('-'*80)

    # 测试所有场景
    correct_count = 0
    total_count = len(scenarios)

    for scenario in scenarios:
        scores = []
        for parent in scenario['parents']:
            score, _, support_bonus = calculate_score(parent, cap=cap)
            scores.append(score)

        winner_idx = scores.index(max(scores))
        winner = scenario['parents'][winner_idx]

        # 判断是否合理（选择 dual_hot 最多的）
        max_dual_hot = max(p['dual_hot'] for p in scenario['parents'])
        is_correct = winner['dual_hot'] == max_dual_hot

        if is_correct:
            correct_count += 1

        status = '✓' if is_correct else '✗'
        print(f'  {scenario["name"]}: {status} {winner["name"]} (support_bonus={support_bonus:.2f})')

    accuracy = correct_count / total_count
    print(f'\n  准确率：{correct_count}/{total_count} = {accuracy:.1%}')

print('\n' + '='*80)
print('结论：是否存在过拟合风险？')
print('='*80)

# 测试当前调整（cap=5.0）
scores_cap5 = []
for scenario in scenarios:
    scores = [calculate_score(p, cap=5.0)[0] for p in scenario['parents']]
    winner = scenario['parents'][scores.index(max(scores))]
    max_dual_hot = max(p['dual_hot'] for p in scenario['parents'])
    if winner['dual_hot'] == max_dual_hot:
        scores_cap5.append(True)
    else:
        scores_cap5.append(False)

accuracy_cap5 = sum(scores_cap5) / len(scores_cap5)

# 测试提高封顶（cap=8.0）
scores_cap8 = []
for scenario in scenarios:
    scores = [calculate_score(p, cap=8.0)[0] for p in scenario['parents']]
    winner = scenario['parents'][scores.index(max(scores))]
    max_dual_hot = max(p['dual_hot'] for p in scenario['parents'])
    if winner['dual_hot'] == max_dual_hot:
        scores_cap8.append(True)
    else:
        scores_cap8.append(False)

accuracy_cap8 = sum(scores_cap8) / len(scores_cap8)

print(f'\n当前方案（cap=5.0）准确率：{accuracy_cap5:.1%}')
print(f'提高封顶方案（cap=8.0）准确率：{accuracy_cap8:.1%}')

if accuracy_cap5 >= 0.67:  # 2/3 以上场景正确
    print('\n✓ 无过拟合风险：至少在67%的场景下选择正确')
elif accuracy_cap8 > accuracy_cap5:
    print('\n✓ 提高封顶阈值可降低过拟合风险')
else:
    print('\n✗ 存在过拟合风险：只在特定场景有效')

print('\n推荐方案：')
if accuracy_cap8 >= accuracy_cap5 and accuracy_cap8 >= 0.67:
    print('  提高封顶阈值到 8（准确率更高，适应性更强）')
else:
    print('  保持当前调整（cap=5.0，准确率可接受）')