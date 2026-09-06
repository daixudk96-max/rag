"""
Phase 3 Batch Judgment - Quick Entry Mode

Shows all 28 judgments in one list, user enters choices in one line.
Example: "A B C A A B C A A A B B C C A A A B A C B A A B C A"
"""

import json
import csv
from pathlib import Path
from typing import NamedTuple

class Judgment(NamedTuple):
    query_id: str
    query_text: str
    hit_rank: int
    node_id: str
    heading_path: str
    page_no: str
    text_preview: str
    is_relevant: bool
    relevance_score: float
    judgment_category: str
    judgment_notes: str

def main():
    # Load retrieval results
    retrieval_file = Path('verification/phase3-real-validation/retrieval_results.json')
    retrieval_data = json.loads(retrieval_file.read_text(encoding='utf-8'))

    # Load template
    template_file = Path('verification/phase3-real-validation/judgment_template.csv')
    template_rows = []

    with template_file.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        template_rows = list(reader)

    # Create query lookup
    query_lookup = {}
    for result in retrieval_data['results']:
        query_lookup[result['query_id']] = {
            'query_text': result['query_text'],
            'category': result['category'],
            'difficulty': result['difficulty'],
        }

    print("=" * 100)
    print("Phase 3 Batch Judgment - Quick Entry Mode")
    print("=" * 100)
    print(f"\nTotal judgments: {len(template_rows)}")
    print("\nINSTRUCTIONS:")
    print("  1. Review the list below (Query + Retrieved Hit)")
    print("  2. For each hit, judge: A(fully) B(partial) C(not)")
    print("  3. Enter ALL choices in one line separated by spaces")
    print("     Example: A B C A A B C A A A B B C C A A A B A C B A A B C A")
    print("\nJudgment options:")
    print("  A = fully_relevant (score: 0.9) - Hit directly answers query")
    print("  B = partially_relevant (score: 0.5) - Hit partially answers")
    print("  C = not_relevant (score: 0.1) - Hit does not answer")
    print("  . = Skip this hit")
    print("=" * 100)

    # Display all judgments
    print(f"\nJUDGMENT LIST (28 total):")
    print("=" * 100)

    for idx, row in enumerate(template_rows, 1):
        query_id = row['query_id']
        query_info = query_lookup.get(query_id, {})

        query_text = query_info.get('query_text', 'N/A')
        heading = row['heading_path']
        preview = row['text_preview'][:60]

        print(f"\n[{idx}] {query_id}-#{row['hit_rank']}")
        print(f"  Q: {query_text[:70]}")
        print(f"  H: {heading} | P:{row['page_no']}")
        print(f"  →: {preview}...")

    print("\n" + "=" * 100)
    print("Enter your 28 judgments (A/B/C/. separated by spaces):")
    print("=" * 100)

    # Get user input
    choices_input = input("\nYour choices: ").strip().upper()

    # Parse choices
    choices = choices_input.split()

    if len(choices) != len(template_rows):
        print(f"\nWARNING: Expected {len(template_rows)} choices, got {len(choices)}")
        if len(choices) < len(template_rows):
            # Pad with default choice
            choices.extend(['B'] * (len(template_rows) - len(choices)))
            print(f"  Auto-filled missing choices with 'B' (partially_relevant)")
        elif len(choices) > len(template_rows):
            choices = choices[:len(template_rows)]
            print(f"  Truncated to first {len(template_rows)} choices")

    # Convert choices to judgments
    judgments = []

    for idx, (choice, row) in enumerate(zip(choices, template_rows), 1):
        query_id = row['query_id']
        query_info = query_lookup.get(query_id, {})

        if choice == 'A':
            is_relevant = True
            relevance_score = 0.9
            judgment_category = 'fully_relevant'
        elif choice == 'B':
            is_relevant = True
            relevance_score = 0.5
            judgment_category = 'partially_relevant'
        elif choice == 'C':
            is_relevant = False
            relevance_score = 0.1
            judgment_category = 'not_relevant'
        elif choice == '.':
            continue  # Skip
        else:
            print(f"  Invalid choice '{choice}' at #{idx}, defaulting to 'B'")
            is_relevant = True
            relevance_score = 0.5
            judgment_category = 'partially_relevant'

        judgment = Judgment(
            query_id=query_id,
            query_text=query_info.get('query_text', ''),
            hit_rank=int(row['hit_rank']),
            node_id=row['node_id'],
            heading_path=row['heading_path'],
            page_no=row['page_no'],
            text_preview=row['text_preview'],
            is_relevant=is_relevant,
            relevance_score=relevance_score,
            judgment_category=judgment_category,
            judgment_notes='',
        )
        judgments.append(judgment)

    # Save judgments
    if judgments:
        output_file = Path('verification/phase3-real-validation/judgment_completed.csv')
        with output_file.open('w', encoding='utf-8', newline='') as f:
            fieldnames = ['query_id', 'query_text', 'hit_rank', 'node_id', 'heading_path',
                          'page_no', 'text_preview', 'is_relevant', 'relevance_score',
                          'judgment_category', 'judgment_notes']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for j in judgments:
                writer.writerow({
                    'query_id': j.query_id,
                    'query_text': j.query_text,
                    'hit_rank': j.hit_rank,
                    'node_id': j.node_id,
                    'heading_path': j.heading_path,
                    'page_no': j.page_no,
                    'text_preview': j.text_preview,
                    'is_relevant': j.is_relevant,
                    'relevance_score': j.relevance_score,
                    'judgment_category': j.judgment_category,
                    'judgment_notes': j.judgment_notes,
                })

        print(f"\n{'='*100}")
        print(f"SUCCESS: Judgment Collection Complete")
        print(f"{'='*100}")
        print(f"  Total judgments saved: {len(judgments)}/{len(template_rows)}")
        print(f"  Output file: {output_file}")

        # Quick summary
        fully_count = sum(1 for j in judgments if j.judgment_category == 'fully_relevant')
        partial_count = sum(1 for j in judgments if j.judgment_category == 'partially_relevant')
        not_count = sum(1 for j in judgments if j.judgment_category == 'not_relevant')

        print(f"\nJudgment distribution:")
        print(f"  Fully relevant: {fully_count} ({fully_count/len(judgments)*100:.1f}%)")
        print(f"  Partially relevant: {partial_count} ({partial_count/len(judgments)*100:.1f}%)")
        print(f"  Not relevant: {not_count} ({not_count/len(judgments)*100:.1f}%)")

        print(f"\n✅ Next step:")
        print(f"   python verification/phase3-real-validation/calculate_metrics.py")

    else:
        print("\nNo judgments collected. Exiting.")

if __name__ == "__main__":
    main()