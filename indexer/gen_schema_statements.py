#!/usr/bin/env python3
"""Generate d1/schema.statements.json — explicit statement list, no SQL parsing."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

stmts = [
  "DROP TRIGGER IF EXISTS chunks_au",
  "DROP TRIGGER IF EXISTS chunks_ad",
  "DROP TRIGGER IF EXISTS chunks_ai",
  "DROP TABLE IF EXISTS chunks_fts",
  "DROP TABLE IF EXISTS chunks",
  """CREATE TABLE chunks (
  id           INTEGER PRIMARY KEY,
  chunk_id     TEXT UNIQUE NOT NULL,
  vendor       TEXT NOT NULL,
  version      TEXT NOT NULL DEFAULT 'latest',
  title        TEXT NOT NULL,
  heading_path TEXT,
  path         TEXT,
  source_url   TEXT NOT NULL,
  license      TEXT NOT NULL,
  attribution  TEXT,
  last_updated TEXT,
  snippet      TEXT,
  content      TEXT NOT NULL
)""",
  "CREATE INDEX idx_chunks_vendor ON chunks(vendor)",
  "CREATE INDEX idx_chunks_chunkid ON chunks(chunk_id)",
  """CREATE VIRTUAL TABLE chunks_fts USING fts5(
  title,
  heading_path,
  content,
  content='chunks',
  content_rowid='id',
  tokenize='porter unicode61'
)""",
  """CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, title, heading_path, content)
  VALUES (new.id, new.title, new.heading_path, new.content);
END""",
  """CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, title, heading_path, content)
  VALUES ('delete', old.id, old.title, old.heading_path, old.content);
END""",
  """CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, title, heading_path, content)
  VALUES ('delete', old.id, old.title, old.heading_path, old.content);
  INSERT INTO chunks_fts(rowid, title, heading_path, content)
  VALUES (new.id, new.title, new.heading_path, new.content);
END""",
]

out = BASE / "d1" / "schema.statements.json"
json.dump(stmts, out.open("w"), indent=1)
print(f"{len(stmts)} statements → {out.name}")
