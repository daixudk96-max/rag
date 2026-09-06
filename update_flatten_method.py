# Read the file
with open('llamaindex_runtime/tree/pageindex_adapter.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line where we process page_no (around line 452-453 in the flatten method)
# Replace the page_no handling to support both PDF and markdown

for i, line in enumerate(lines):
    if '# 3. Use start_index as page_no, ignore end_index' in line:
        # Replace the next line as well
        lines[i] = '''            # 3. Use start_index (PDF) or line_num (markdown) as page_no
            # PDF structure: start_index/end_index (page numbers)
            # Markdown structure: line_num (line numbers, not pages)
            page_no = node_dict.get("start_index") or node_dict.get("line_num")
'''
        # Remove the old line that just got page_no = node_dict.get("start_index")
        if i+1 < len(lines) and 'page_no = node_dict.get("start_index")' in lines[i+1]:
            lines[i+1] = ''
        break

# Write back
with open('llamaindex_runtime/tree/pageindex_adapter.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Updated _flatten_embedded_tree to support both PDF and markdown")
