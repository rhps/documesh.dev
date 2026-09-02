-- Documesh search — D1 schema (Phase 1, Option C)
-- chunks: canonical doc rows. chunks_fts: external-content FTS5 index over it.
--
-- FTS5 external-content layout: the FTS table's columns must be declared in
-- the SAME ORDER as the content table columns they index, and the content
-- table's INTEGER PRIMARY KEY maps to the FTS rowid automatically.
-- We index title, heading_path, content (bm25 weights follow that order).

DROP TRIGGER IF EXISTS chunks_au;
DROP TRIGGER IF EXISTS chunks_ad;
DROP TRIGGER IF EXISTS chunks_ai;
DROP TABLE IF EXISTS chunks_fts;
DROP TABLE IF EXISTS chunks;

CREATE TABLE chunks (
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
);

CREATE INDEX idx_chunks_vendor   ON chunks(vendor);
CREATE INDEX idx_chunks_chunkid  ON chunks(chunk_id);

CREATE VIRTUAL TABLE chunks_fts USING fts5(
  title,
  heading_path,
  content,
  content='chunks',
  content_rowid='id',
  tokenize='porter unicode61'
);

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, title, heading_path, content)
  VALUES (new.id, new.title, new.heading_path, new.content);
END;

CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, title, heading_path, content)
  VALUES ('delete', old.id, old.title, old.heading_path, old.content);
END;

CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, title, heading_path, content)
  VALUES ('delete', old.id, old.title, old.heading_path, old.content);
  INSERT INTO chunks_fts(rowid, title, heading_path, content)
  VALUES (new.id, new.title, new.heading_path, new.content);
END;
