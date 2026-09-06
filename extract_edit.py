import json

agent_path = "C:/Users/daixu/.claude/projects/E--github-rag/616f0848-bf71-4b8d-9641-687e3f62bf7d/subagents/agent-ad8c431e2401540af.jsonl"

with open(agent_path, 'r', encoding='utf-8') as f:
    for lineno, line in enumerate(f, 1):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = obj.get('timestamp','')
        if obj.get('type') in ('user','assistant'):
            content = obj.get('message', {}).get('content')
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'tool_use':
                        name = item.get('name')
                        tiid = item.get('id')
                        inp = item.get('input', {})
                        if name == 'Edit':
                            path_f = inp.get('file_path','') or ''
                            if 'test_e2a_desired_state' in path_f:
                                old = inp.get('old_string','')
                                new = inp.get('new_string','')
                                print(f"line={lineno} ts={ts}")
                                print(f"old_len={len(old)} new_len={len(new)}")
                                # Save to files in current directory
                                with open('edit_old.txt', 'w', encoding='utf-8', newline='\n') as f:
                                    f.write(old)
                                with open('edit_new.txt', 'w', encoding='utf-8', newline='\n') as f:
                                    f.write(new)
                                print("Saved old/new to edit_old.txt and edit_new.txt")
