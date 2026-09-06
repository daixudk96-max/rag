"""
Phase 3 Interactive Judgment Collector

Asks user one-by-one to judge retrieval hits and saves to judgment_completed.csv.
"""

import json
import csv
import sys
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
        for row in reader:
            template_rows.append(row)

    # Create query lookup
    query_lookup = {}
    for result in retrieval_data['results']:
        query_lookup[result['query_id']] = {
            'query_text': result['query_text'],
            'category': result['category'],
            'difficulty': result['difficulty'],
        }

    judgments = []

    print("=" * 80)
    print("Phase 3 Interactive Manual Judgment")
    print("=" * 80)
    print(f"\nTotal hits to judge: {len(template_rows)}")
    print(f"\nFor each hit, you will choose:")
    print(f"  A) fully_relevant    - Hit directly answers the query (score: 0.9)")
    print(f"  B) partially_relevant - Hit partially answers (score: 0.5)")
    print(f"  C) not_relevant      - Hit does not answer (score: 0.1)")
    print(f"\nPress Ctrl+C to quit early (partial judgments will be saved)")
    print("=" * 80)

    try:
        for idx, row in enumerate(template_rows, 1):
            query_id = row['query_id']
            query_info = query_lookup.get(query_id, {})

            print(f"\n{'='*80}")
            print(f"[{idx}/{len(template_rows)}] Judgment for {query_id} - Hit #{row['hit_rank']}")
            print(f"{'='*80}")
            print(f"\nQUERY:")
            print(f"  {query_info.get('query_text', 'N/A')}")
            print(f"  Category: {query_info.get('category', 'N/A')}, Difficulty: {query_info.get('difficulty', 'N/A')}")
            print(f"\nRETRIEVED HIT:")
            print(f"  Heading: {row['heading_path']}")
            print(f"  Page: {row['page_no']}")
            print(f"  Preview: {row['text_preview'][:80]}...")

            # Ask user choice
            print(f"\nYOUR JUDGMENT:")
            print(f"  A) fully_relevant (score: 0.9)")
            print(f"  B) partially_relevant (score: 0.5)")
            print(f"  C) not_relevant (score: 0.1)")
            print(f"  D) Skip this hit")

            choice = input("\nChoose A/B/C/D: ").strip().upper()

            if choice == 'A':
                is_relevant = True
                relevance_score = 0.9
                judgment_category = 'fully_relevant'
                judgment_notes = input("Optional notes (press Enter to skip): ").strip()
            elif choice == 'B':
                is_relevant = True
                relevance_score = 0.5
                judgment_category = 'partially_relevant'
                judgment_notes = input("Optional notes (press Enter to skip): ").strip()
            elif choice == 'C':
                is_relevant = False
                relevance_score = 0.1
                judgment_category = 'not_relevant'
                judgment_notes = input("Optional notes (press Enter to skip): ").strip()
            elif choice == 'D':
                print("Skipping...")
                continue
            else:
                print("Invalid choice, defaulting to 'partially_relevant'")
                is_relevant = True
                relevance_score = 0.5
                judgment_category = 'partially_relevant'
                judgment_notes = ''

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
                judgment_notes=judgment_notes,
            )
            judgments.append(judgment)

            print(f"  ✓ Recorded: {judgment_category} (score: {relevance_score})")

    except KeyboardInterrupt:
        print(f"\n\nInterrupted! Saving {len(judgments)} judgments collected so far...")

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

        print(f"\n{'='*80}")
        print(f"Judgment Collection Complete")
        print(f"{'='*80}")
        print(f"  Total judgments: {len(judgments)}/{len(template_rows)}")
        print(f"  Saved to: {output_file}")

        if len(judgments) == len(template_rows):
            print(f"\n✅ All judgments complete!")
            print(f"Next step: python verification/phase3-real-validation/calculate_metrics.py")
        else:
            print(f"\n⚠️ Partial judgments saved ({len(judgments)}/{len(template_rows)})")
            print(f"Re-run this script to continue")
    else:
        print("\nNo judgments collected. Exiting.")

if __name__ == "__main__":
    main()