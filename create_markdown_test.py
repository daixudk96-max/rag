test_content = """\"\"\"PageIndexTreeAdapter: Markdown file processing tests.

Tests verify that PageIndexTreeAdapter can handle markdown files.
\"\"\""""

with open('tests/llamaindex_runtime/test_pageindex_adapter_markdown.py', 'w', encoding='utf-8') as f:
    f.write(test_content)
print("Created test file")
