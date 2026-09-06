#!/usr/bin/env python3
"""Final correct formula: Three-dimensional weighted average"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print('='*80)
print('最终正确方案：三维加权平均')
print('='*80)

print('\n用户核心观点："命中的子节点加分数求和，除以所有子节点"')
print('\n关键补充：还需考虑"命中子节点的绝对数量"')

print('\n热点的三维定义:')
print('  1. 覆盖率：dual_hot / total（惩罚无关子节点）')
print('  2. 质量：dual_hot子节点的平均相似度')
print('  3. 数量：dual_hot子节点的绝对数量（打破完美覆盖率）')

print('\n' + '='*80)
print('公式推导')
print('='*80)

print('\n步骤1: 计算平均分（用户建议）')
print('  avg_score = Σ(child_score) / total_children')
print('  其中:')
print('    dual_hot子节点: child_score = similarity')
print('    无关子节点: child_score = 0')
print('')
print('  简化:')
print('  avg_score = (dual_hot_count * avg_hot_sim) / total')

print('\n步骤2: 引入数量权重')
print('  avg_score * (dual_hot_count / scaling_factor)')
print('  其中 scaling_factor = 5（归一化）')

print('\n步骤3: 综合公式')
print('  parent_score = avg_score * (dual_hot_count / 5.0)')
print('                = (dual_hot_count * avg_hot_sim / total) * (dual_hot_count / 5.0)')
print('                = avg_hot_sim * coverage_ratio * support_factor')

print('\n最终公式:')
print('  parent_score = avg_hot_sim * coverage_ratio * support_factor')
print('  其中 support_factor = dual_hot_count / 5.0')

print('\n语义:')
print('  - avg_hot_sim: 命中质量')
print('  - coverage_ratio: 命中比例（惩罚无关子节点）')
print('  - support_factor: 命中数量权重（打破完美覆盖率）')

print('\n' + '='*80)
print('验证最终公式')
print('='*80)

def final_formula(parent):
    """最终公式：三维加权"""
    avg_hot_sim = parent['avg_hot_sim']
    coverage_ratio = parent['dual_hot'] / parent['total']
    support_factor = parent['dual_hot'] / 5.0

    score = avg_hot_sim * coverage_ratio * support_factor
    return score, avg_hot_sim, coverage_ratio, support_factor

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

correct_count = 0

for scenario in scenarios:
    print(f'\n{scenario["name"]}:')
    print('-'*80)

    scores = []
    for parent in scenario['parents']:
        score, avg_sim, coverage, support = final_formula(parent)

        print(f'{parent["name"]}:')
        print(f'  avg_hot_sim={avg_sim:.2f}')
        print(f'  coverage_ratio={coverage:.2f}')
        print(f'  support_factor={parent["dual_hot"]}/5.0={support:.2f}')
        print(f'  score = {avg_sim:.2f} * {coverage:.2f} * {support:.2f} = {score:.4f}')
        print()

        scores.append(score)

    winner = scenario['parents'][scores.index(max(scores))]
    max_dual_hot = max(p['dual_hot'] for p in scenario['parents'])

    if winner['dual_hot'] == max_dual_hot:
        correct_count += 1
        print(f'✓ 选择 {winner["name"]} (dual_hot={winner["dual_hot"]})')
    else:
        print(f'✗ 选择 {winner["name"]} (dual_hot={winner["dual_hot"]} vs max={max_dual_hot})')

accuracy = correct_count / len(scenarios)

print('\n' + '='*80)
print('准确率总结')
print('='*80)

print(f'\n最终公式准确率: {correct_count}/{len(scenarios)} = {accuracy:.1%}')

if accuracy == 1.0:
    print('\n✓ 完美！所有场景正确')
    print('\n这证明了用户观点的正确性，同时补充了"数量权重"的必要性')
else:
    print(f'\n准确率{accuracy:.1%}，仍有优化空间')

print('\n' + '='*80)
print('为什么最终公式有效？')
print('='*80)

print('\nPhase 14场景分析:')
print('  Parent A:')
print('    avg_hot_sim=0.53, coverage_ratio=1.00（完美）, support_factor=2/5=0.4')
print('    score = 0.53 * 1.00 * 0.4 = 0.2120')
print('')
print('  Parent B:')
print('    avg_hot_sim=0.57, coverage_ratio=0.71（中等）, support_factor=5/5=1.0')
print('    score = 0.57 * 0.71 * 1.0 = 0.4047')
print('')
print('  Parent B胜出！')
print('  关键：support_factor打破了Parent A的完美覆盖率优势')
print('  Parent A虽然coverage=1.0，但dual_hot_count=2 → support_factor=0.4')
print('  Parent B虽然coverage=0.71，但dual_hot_count=5 → support_factor=1.0')
print('  数量优势补偿了覆盖率劣势！')

print('\n极端例子分析:')
print('  Parent C (95无关子节点):')
print('    avg_hot_sim=0.80, coverage_ratio=0.05（极低）, support_factor=5/5=1.0')
print('    score = 0.80 * 0.05 * 1.0 = 0.0400（严重惩罚！）')
print('')
print('  Parent D (7无关子节点):')
print('    avg_hot_sim=0.60, coverage_ratio=0.30, support_factor=3/5=0.6')
print('    score = 0.60 * 0.30 * 0.6 = 0.1080')
print('')
print('  Parent D胜出！')
print('  关键：coverage_ratio严重惩罚了Parent C的大量无关子节点')

print('\n高质量低覆盖分析:')
print('  Parent E:')
print('    avg_hot_sim=0.90, coverage_ratio=0.20, support_factor=10/5=2.0')
print('    score = 0.90 * 0.20 * 2.0 = 0.3600')
print('')
print('  Parent F:')
print('    avg_hot_sim=0.70, coverage_ratio=0.40, support_factor=8/5=1.6')
print('    score = 0.70 * 0.40 * 1.6 = 0.4480')
print('')
print('  Parent F胜出！')
print('  关键：虽然Parent E有更多dual_hot，但coverage太低')
print('  coverage_ratio平衡了数量和质量')

print('\n' + '='*80)
print('结论')
print('='*80)

print('\n用户的质疑完全正确:')
print('  ✓ 线性相加语义错误（三个因子互相打架）')
print('  ✓ 应该用平均分（惩罚无关子节点）')
print('  ✓ 平均分逻辑："命中的子节点加分数求和，除以所有子节点"')

print('\n但需要一个关键补充:')
print('  ✓ 引入"命中数量权重"打破完美覆盖率')
print('  ✓ 最终公式：avg_hot_sim * coverage_ratio * support_factor')
print('  ✓ 三维平衡：质量 × 覆盖率 × 数量')

print('\n当前线性相加公式的根本缺陷:')
print('  ✗ coverage_ratio, avg_child_vector, support_bonus 线性相加')
print('  ✗ 无语义统一性')
print('  ✗ 过度偏向"完美覆盖率"父节点')
print('  ✗ 无法惩罚"大量无关子节点"')

print('\n应该修改为:')
print('  ✓ parent_score = avg_hot_sim * coverage_ratio * (dual_hot_count / 5.0)')
print('  ✓ 或保持当前权重分配（coverage=0.30, support=0.30）')
print('  ✓ 但改为乘法而非加法！')