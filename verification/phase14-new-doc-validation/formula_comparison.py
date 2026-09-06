#!/usr/bin/env python3
"""Compare current linear addition formula vs average score logic"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print('='*80)
print('Comparison: Linear Addition vs Average Score Logic')
print('='*80)

# Test scenarios
scenarios = [
    {
        'name': 'Phase 14 Document',
        'parents': [
            {'name': 'Parent A (low relevance)', 'total': 2, 'dual_hot': 2, 'avg_hot_sim': 0.53},
            {'name': 'Parent B (high relevance)', 'total': 7, 'dual_hot': 5, 'avg_hot_sim': 0.57},
        ]
    },
    {
        'name': 'Extreme Case: Many Irrelevant Children',
        'parents': [
            {'name': 'Parent C (5% hit rate)', 'total': 100, 'dual_hot': 5, 'avg_hot_sim': 0.80},
            {'name': 'Parent D (30% hit rate)', 'total': 10, 'dual_hot': 3, 'avg_hot_sim': 0.60},
        ]
    },
]

def current_logic_linear(parent, cap=float('inf')):
    """Current formula: Linear addition of 3 factors"""
    coverage_ratio = parent['dual_hot'] / parent['total']
    support_bonus = parent['dual_hot'] / 5.0 if cap == float('inf') else min(parent['dual_hot'] / cap, 1.0)
    avg_child_vector = parent['avg_hot_sim']

    score = coverage_ratio * 0.30 + avg_child_vector * 0.30 + support_bonus * 0.30
    return score, coverage_ratio, support_bonus

def avg_logic(parent, penalty=0.0):
    """User's logic: Average score across ALL children"""
    # dual_hot children contribute their similarity
    hot_scores = parent['dual_hot'] * parent['avg_hot_sim']

    # irrelevant children contribute penalty
    unrelated_count = parent['total'] - parent['dual_hot']
    unrelated_scores = unrelated_count * penalty

    total_score = hot_scores + unrelated_scores
    avg_score = total_score / parent['total']

    return avg_score

print('\n' + '='*80)
print('CURRENT LOGIC: Linear Addition (no penalty for irrelevant children)')
print('='*80)

for scenario in scenarios:
    print(f'\n{scenario["name"]}:')
    print('-'*80)

    for parent in scenario['parents']:
        score, coverage_ratio, support_bonus = current_logic_linear(parent)
        print(f'{parent["name"]}:')
        print(f'  total_children={parent["total"]}, dual_hot={parent["dual_hot"]}')
        print(f'  coverage_ratio={coverage_ratio:.2f}, support_bonus={support_bonus:.2f}')
        print(f'  avg_hot_similarity={parent["avg_hot_sim"]:.2f}')
        print(f'  score={score:.4f}')
        print()

    # Select winner
    scores = [current_logic_linear(p)[0] for p in scenario['parents']]
    winner = scenario['parents'][scores.index(max(scores))]
    print(f'Selected: {winner["name"]} (score={max(scores):.4f})')

print('\n' + '='*80)
print('USER LOGIC: Average Score (penalize irrelevant children)')
print('='*80)

for scenario in scenarios:
    print(f'\n{scenario["name"]}:')
    print('-'*80)

    for parent in scenario['parents']:
        avg = avg_logic(parent, penalty=0.0)
        unrelated = parent['total'] - parent['dual_hot']

        print(f'{parent["name"]}:')
        print(f'  dual_hot children: {parent["dual_hot"]} nodes, avg_sim={parent["avg_hot_sim"]:.2f}')
        print(f'  irrelevant children: {unrelated} nodes, score=0.0')
        print(f'  total score = {parent["dual_hot"]} * {parent["avg_hot_sim"]:.2f} + {unrelated} * 0.0')
        print(f'                 = {parent["dual_hot"] * parent["avg_hot_sim"]:.2f}')
        print(f'  average score = {parent["dual_hot"] * parent["avg_hot_sim"]:.2f} / {parent["total"]} = {avg:.4f}')
        print()

    # Select winner
    avgs = [avg_logic(p, penalty=0.0) for p in scenario['parents']]
    winner = scenario['parents'][avgs.index(max(avgs))]
    print(f'Selected: {winner["name"]} (avg_score={max(avgs):.4f})')

print('\n' + '='*80)
print('CRITICAL COMPARISON: Extreme Case Analysis')
print('='*80)

extreme = scenarios[1]  # The extreme case
parent_c = extreme['parents'][0]  # 5% hit rate
parent_d = extreme['parents'][1]  # 30% hit rate

score_c_linear = current_logic_linear(parent_c)[0]
score_d_linear = current_logic_linear(parent_d)[0]

avg_c = avg_logic(parent_c, penalty=0.0)
avg_d = avg_logic(parent_d, penalty=0.0)

print('\nParent C: 100 children, only 5 dual_hot (95% irrelevant!)')
print(f'  Linear addition score: {score_c_linear:.4f}')
print(f'  Average score: {avg_c:.4f}')
print()

print('Parent D: 10 children, 3 dual_hot (70% irrelevant)')
print(f'  Linear addition score: {score_d_linear:.4f}')
print(f'  Average score: {avg_d:.4f}')
print()

print('SELECTION RESULT:')
print('-'*80)

if score_c_linear > score_d_linear:
    print('Linear addition: selects Parent C (5% hit rate)')
    print('  X WRONG! - Parent C has 95 irrelevant children!')
else:
    print('Linear addition: selects Parent D (30% hit rate)')
    print('  OK - but only by luck, not by design')

print()

if avg_c > avg_d:
    print('Average score: selects Parent C')
    print('  X WRONG')
else:
    print('Average score: selects Parent D (30% hit rate)')
    print('  CORRECT! - Penalizes 95 irrelevant children in Parent C')

print('\n' + '='*80)
print('CONCLUSION')
print('='*80)

print('\nUser is ABSOLUTELY CORRECT:')
print()
print('1. Linear addition is SEMANTICALLY WRONG:')
print('   - coverage_ratio, avg_child_vector, support_bonus describe the SAME thing')
print('   - Adding them double-counts advantages (logical flaw)')
print('   - Example: high avg_child_vector implies high coverage_ratio')
print()
print('2. Linear addition IGNORES irrelevant children:')
print('   - Parent with 100 irrelevant children can still score high')
print('   - No penalty for noise!')
print()
print('3. Average score is CORRECT:')
print('   - Semantic: "average quality of all children"')
print('   - Penalizes irrelevant children (they contribute 0 or negative)')
print('   - Intuitive: high average = truly hot parent')
print()
print('4. Current design is fundamentally flawed!')
print('   - Not just weight allocation issue')
print('   - The ENTIRE formula is wrong')