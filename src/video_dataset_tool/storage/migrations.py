SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE source_videos (
    id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    file_size_bytes INTEGER,
    mtime_ns INTEGER,
    duration_ms INTEGER,
    fps_num INTEGER, fps_den INTEGER,
    width INTEGER, height INTEGER,
    video_codec TEXT, audio_codec TEXT,
    availability TEXT NOT NULL DEFAULT 'present',
    created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL
);
CREATE TABLE clips (
    id TEXT PRIMARY KEY,
    source_video_id TEXT NOT NULL REFERENCES source_videos(id),
    source_path_snapshot TEXT NOT NULL,
    source_size_bytes INTEGER, source_mtime_ns INTEGER,
    requested_in_ms INTEGER NOT NULL CHECK(requested_in_ms >= 0),
    requested_out_ms INTEGER NOT NULL CHECK(requested_out_ms > requested_in_ms),
    event_start_ms INTEGER, event_end_ms INTEGER,
    actual_start_ms INTEGER, actual_duration_ms INTEGER,
    category TEXT NOT NULL CHECK(category IN ('positive','hard_negative','normal','uncertain')),
    object_type TEXT, notes TEXT,
    review_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK(review_status IN ('unreviewed','reviewed')),
    cut_mode TEXT NOT NULL CHECK(cut_mode IN ('fast','precise')),
    cut_precision TEXT DEFAULT 'unknown' CHECK(cut_precision IN ('approximate','verified','unknown')),
    output_root TEXT NOT NULL,
    output_path TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending','processing','completed','failed','cancelled')),
    error_message TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX clips_filters ON clips(source_video_id, category, status);
CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE drafts (
    source_video_id TEXT PRIMARY KEY REFERENCES source_videos(id),
    draft_json TEXT NOT NULL
);
"""


def migrate(connection):
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise ValueError(
            "Database được tạo bởi phiên bản mới hơn. Hãy dùng phiên bản ứng dụng phù hợp."
        )
    if version == 0:
        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n" + SCHEMA + "\nPRAGMA user_version=1;\nCOMMIT;"
            )
        except Exception:
            connection.rollback()
            raise
