#!/usr/bin/env python3
"""Test autocommit auto-enable"""

import os, sys
import psycopg
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / '.env', override=False)

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

db_url = os.environ['DATABASE_URL']
conn = psycopg.connect(db_url)  # No autocommit

print(f'Connection autocommit before registry: {conn.autocommit}')

registry = PostgresRegistryWriter(conn)

print(f'Connection autocommit after registry: {conn.autocommit}')

conn.close()