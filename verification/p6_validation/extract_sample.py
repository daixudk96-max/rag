"""Extract 1/3 of p6_final.md (approximately 20 heading entries) for validation.

This avoids torch loading issues by creating a smaller test document.
"""
from pathlib import Path

SOURCE_FILE = Path("E:/obsidisen/默认/p6_final.md")
OUTPUT_FILE = Path("E:/github/rag/verification/p6_validation/p6_final_sample.md")

# Extract lines 1-200 (approximately 1/3 of the 602-line document)
source_lines = SOURCE_FILE.read_text(encoding="utf-8").splitlines()
sample_lines = source_lines[:200]

# Write sample document
OUTPUT_FILE.write_text("\n".join(sample_lines), encoding="utf-8")

print(f"Extracted {len(sample_lines)} lines from {SOURCE_FILE}")
print(f"Output: {OUTPUT_FILE}")
print(f"Sample covers time-stamps: 00:01, 00:31, 01:41, 02:16, 03:02")
print(f"Approximately 20 heading entries after preprocessing")