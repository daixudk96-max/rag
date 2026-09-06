import psycopg
conn_str = "postgresql://postgres:postgres@localhost:5432/rag"
with psycopg.connect(conn_str) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM tree_nodes;")
        nodes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM vector_chunks;")
        chunks = cur.fetchone()[0]
        cur.execute("SELECT MAX(level_no) FROM tree_nodes;")
        max_level = cur.fetchone()[0]
        print(f"tree_nodes={nodes}, chunks={chunks}, max_level={max_level}")
        if nodes > 0:
            cur.execute("SELECT heading_path FROM tree_nodes WHERE level_no=0 LIMIT 1;")
            root = cur.fetchone()[0]
            print(f"root_heading={root[:50]}...")