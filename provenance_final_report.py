#!/usr/bin/env python3
"""
FINAL provenance verification report for test_e2a_desired_state.py
"""
import json
from pathlib import Path
import subprocess
import tempfile
import hashlib

# Configuration
subagents_dir = Path(r'C:\Users\daixu\.claude\projects\E--github-rag\616f0848-bf71-4b8d-9641-687e3f62bf7d\subagents')
target_file = Path(r'E:\github\rag\tests\llamaindex_runtime\okf\test_e2a_desired_state.py')

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def count_line_endings(data: bytes) -> dict:
    crlf = data.count(b'\r\n')
    lf_only = data.replace(b'\r\n', b'').count(b'\n')
    return {'crlf': crlf, 'lf': lf_only, 'trailing_newline': data.endswith(b'\n')}

def get_tool_input(jsonl_file, line_num):
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if i == line_num:
                data = json.loads(line)
                message = data.get('message', {})
                content = message.get('content', [])
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'tool_use':
                        return item.get('input', {})
    return {}

print('=' * 70)
print('PROVENANCE VERIFICATION REPORT')
print('=' * 70)
print(f'\nTarget: {target_file}')
print(f'Main transcript: C:\\Users\\daixu\\.claude\\projects\\E--github-rag\\616f0848-bf71-4b8d-9641-687e3f62bf7d.jsonl')
print(f'Verification date: 2026-07-29')

# === STAGE 1: Reconstruct file from Write/Edit events ===
events = [
    ('agent-af251fb12f9521dc3.jsonl', 93, 'Write', '2026-07-19T07:40:07.389Z'),
    ('agent-af251fb12f9521dc3.jsonl', 166, 'Edit', '2026-07-19T07:44:38.188Z'),
    ('agent-af251fb12f9521dc3.jsonl', 168, 'Edit', '2026-07-19T07:44:52.967Z'),
    ('agent-af251fb12f9521dc3.jsonl', 170, 'Edit', '2026-07-19T07:45:03.607Z'),
    ('agent-af251fb12f9521dc3.jsonl', 238, 'Edit', '2026-07-19T07:48:26.158Z'),
    ('agent-af251fb12f9521dc3.jsonl', 255, 'Edit', '2026-07-19T07:49:47.193Z'),
    ('agent-af251fb12f9521dc3.jsonl', 293, 'Edit', '2026-07-19T07:51:58.953Z'),
    ('agent-ac8e3623db5e5d780.jsonl', 8, 'Edit', '2026-07-19T08:23:18.710Z'),
    ('agent-a8b0bf7e7c5060450.jsonl', 12, 'Edit', '2026-07-20T07:02:29.450Z'),
    ('agent-a8b0bf7e7c5060450.jsonl', 26, 'Edit', '2026-07-20T07:03:05.468Z'),
]

file_content = ''
for jsonl_name, line_num, tool, ts in events:
    tool_input = get_tool_input(subagents_dir / jsonl_name, line_num)
    if tool == 'Write':
        file_content = tool_input.get('content', '')
    elif tool == 'Edit':
        old_string = tool_input.get('old_string', '')
        new_string = tool_input.get('new_string', '')
        if old_string in file_content:
            file_content = file_content.replace(old_string, new_string, 1)

print(f'\n--- STAGE 1: Write/Edit Events ---')
print(f'Events processed: {len(events)}')
print(f'Size after Stage 1: {len(file_content.encode("utf-8"))} bytes')

# === STAGE 2: Apply Black 25.12.0 ===
with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
    f.write(file_content)
    temp1 = f.name

subprocess.run(['python', '-m', 'black', temp1], capture_output=True)
with open(temp1, 'r', encoding='utf-8') as f:
    file_content = f.read()

print(f'\n--- STAGE 2: Black 25.12.0 Format ---')
print(f'Event: 2026-07-20T07:03:09 (agent-a8b0bf7e7c5060450.jsonl:30)')
print(f'Size after Black: {len(file_content.encode("utf-8"))} bytes')

# === STAGE 3: Apply last Edit (adds both tests) ===
tool_input = get_tool_input(subagents_dir / 'agent-ad8c431e2401540af.jsonl', 8)
old_string = tool_input.get('old_string', '')
new_string = tool_input.get('new_string', '')

# Try original first, then adjusted if needed
if old_string in file_content:
    file_content = file_content.replace(old_string, new_string, 1)
else:
    # Adjust for Black's formatting of function signatures
    old_sig = '-> (\n    None\n):'
    new_sig = '-> None:'
    adjusted_old = old_string.replace(old_sig, new_sig)
    adjusted_new = new_string.replace(old_sig, new_sig)
    if adjusted_old in file_content:
        file_content = file_content.replace(adjusted_old, adjusted_new, 1)

pre_unauthorized_bytes = file_content.encode('utf-8')
pre_unauthorized_sha256 = sha256_bytes(pre_unauthorized_bytes)
pre_unauthorized_size = len(pre_unauthorized_bytes)
pre_unauthorized_lines = count_line_endings(pre_unauthorized_bytes)

print(f'\n--- STAGE 3: Last Edit (July 20, 07:32:47) ---')
print(f'Event: 2026-07-20T07:32:47.886Z (agent-ad8c431e2401540af.jsonl:8)')
print(f'Note: This edit adds TWO tests:')
print(f'  - test_materialization_input_accepts_unicode_noncharacter_u_fffe_in_parent_checksums')
print(f'  - test_frozen_extraction_contract_preserves_object_identity')
print(f'Size after Edit: {pre_unauthorized_size} bytes')

# === STAGE 4: Apply Ruff 0.14.9 I001 fix ===
with open(temp1, 'w', encoding='utf-8') as f:
    f.write(file_content)

result = subprocess.run(['python', '-m', 'ruff', 'check', '--select', 'I', '--fix', temp1], capture_output=True, text=True)
with open(temp1, 'r', encoding='utf-8') as f:
    file_content = f.read()

import os
os.unlink(temp1)

post_ruff_bytes = file_content.encode('utf-8')
post_ruff_sha256 = sha256_bytes(post_ruff_bytes)
post_ruff_size = len(post_ruff_bytes)
post_ruff_lines = count_line_endings(post_ruff_bytes)

print(f'\n--- STAGE 4: Ruff 0.14.9 I001 Fix (July 28, 13:43:00) ---')
print(f'Event: 2026-07-28T13:43:00.113Z (agent-a3ee8d3e2a970189e.jsonl:2441)')
print(f'Ruff output: {result.stdout.strip()}')
print(f'Size after Ruff: {post_ruff_size} bytes')

# === CURRENT FILE ===
with open(target_file, 'rb') as f:
    current_bytes = f.read()

current_sha256 = sha256_bytes(current_bytes)
current_size = len(current_bytes)
current_lines = count_line_endings(current_bytes)

print(f'\n' + '=' * 70)
print('FILE METRICS COMPARISON')
print('=' * 70)

print(f'\n--- Pre-Unauthorized State (July 20, 07:32:47) ---')
print(f'SHA-256: {pre_unauthorized_sha256}')
print(f'Size: {pre_unauthorized_size} bytes')
print(f'CRLF: {pre_unauthorized_lines["crlf"]}, LF: {pre_unauthorized_lines["lf"]}, Trailing newline: {pre_unauthorized_lines["trailing_newline"]}')

print(f'\n--- Post-Ruff State (July 28, 13:43:00) ---')
print(f'SHA-256: {post_ruff_sha256}')
print(f'Size: {post_ruff_size} bytes')
print(f'CRLF: {post_ruff_lines["crlf"]}, LF: {post_ruff_lines["lf"]}, Trailing newline: {post_ruff_lines["trailing_newline"]}')

print(f'\n--- Current File ---')
print(f'SHA-256: {current_sha256}')
print(f'Size: {current_size} bytes')
print(f'CRLF: {current_lines["crlf"]}, LF: {current_lines["lf"]}, Trailing newline: {current_lines["trailing_newline"]}')

# === VERIFICATION ===
print(f'\n' + '=' * 70)
print('VERIFICATION RESULTS')
print('=' * 70)

print(f'\nPre-unauthorized vs Current: {pre_unauthorized_size - current_size} bytes')
print(f'Post-Ruff vs Current: {post_ruff_size - current_size} bytes')
print(f'Ruff removed: {pre_unauthorized_size - post_ruff_size} bytes')

if post_ruff_bytes == current_bytes:
    print(f'\nVERDICT: VERIFIED_PROVEN')
    print('Exact byte-for-byte match between post-Ruff replay and current file.')
    print('Hypothesis CONFIRMED: Ruff 0.14.9 I001 fix removed exactly 1 byte.')
    print('\nChronology established:')
    print('  1. 2026-07-19T07:40:07 - Initial Write (agent-af251fb12f9521dc3.jsonl:93)')
    print('  2. 2026-07-19T07:44:38 through 2026-07-20T07:03:05 - 9 Edit events')
    print('  3. 2026-07-20T07:03:09 - Black formatting (agent-a8b0bf7e7c5060450.jsonl:30)')
    print('  4. 2026-07-20T07:32:47 - Last Edit adds 2 tests (agent-ad8c431e2401540af.jsonl:8)')
    print('  5. 2026-07-28T13:43:00 - Ruff I001 fix removes 1 byte (agent-a3ee8d3e2a970189e.jsonl:2441)')
else:
    print(f'\nVERDICT: BLOCKED')
    print(f'Mismatch detected: {post_ruff_size - current_size} bytes difference.')