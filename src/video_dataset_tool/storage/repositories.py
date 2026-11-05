import csv
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..core.models import ClipRequest, ExportResult, VideoMetadata
from ..core.paths import canonical_path
from ..core.validators import validate_request
from .database import Database


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Repository:
    def __init__(self, database: Database):
        self.database = database
        self.connection = database.connection

    def ensure_source(self, path: str | Path) -> dict:
        key = canonical_path(path)
        row = self.connection.execute(
            "SELECT * FROM source_videos WHERE source_path=?", (key,)
        ).fetchone()
        if row:
            return dict(row)
        stamp = utc_now()
        try:
            stat = Path(key).stat()
            size, mtime, availability = stat.st_size, stat.st_mtime_ns, "present"
        except OSError:
            size, mtime, availability = None, None, "missing"
        with self.connection:
            self.connection.execute(
                "INSERT INTO source_videos(id,source_path,display_name,file_size_bytes,mtime_ns,availability,created_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?)",
                (str(uuid4()), key, Path(path).name, size, mtime, availability, stamp, stamp),
            )
        return dict(
            self.connection.execute(
                "SELECT * FROM source_videos WHERE source_path=?", (key,)
            ).fetchone()
        )

    def update_source(self, source_id: str, metadata: VideoMetadata):
        row = self.connection.execute(
            "SELECT source_path FROM source_videos WHERE id=?", (source_id,)
        ).fetchone()
        stat = Path(row[0]).stat()
        fields = asdict(metadata)
        fields.update(
            file_size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            availability="present",
            last_seen_at=utc_now(),
        )
        with self.connection:
            self.connection.execute(
                "UPDATE source_videos SET "
                + ",".join(f"{key}=?" for key in fields)
                + " WHERE id=?",
                (*fields.values(), source_id),
            )

    def sources(self) -> list[dict]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM source_videos ORDER BY created_at,source_path"
            )
        ]

    def refresh_availability(self):
        with self.connection:
            for row in self.sources():
                try:
                    stat = Path(row["source_path"]).stat()
                    state = (
                        "present"
                        if (stat.st_size, stat.st_mtime_ns)
                        == (row["file_size_bytes"], row["mtime_ns"])
                        else "changed"
                    )
                except OSError:
                    state = "missing"
                self.connection.execute(
                    "UPDATE source_videos SET availability=? WHERE id=?", (state, row["id"])
                )

    def create_clip(self, request: ClipRequest, output_root: Path):
        validate_request(request)
        fields = asdict(request)
        fields.pop("metadata")
        fields["source_path_snapshot"] = fields.pop("source_path")
        fields["source_size_bytes"] = fields.pop("source_size")
        fields["source_mtime_ns"] = fields.pop("source_mtime_ns")
        fields.update(
            output_root=str(Path(output_root).resolve()),
            status="pending",
            cut_precision="approximate" if request.cut_mode == "fast" else "unknown",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        with self.connection:
            self.connection.execute(
                f"INSERT INTO clips ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
                tuple(fields.values()),
            )

    def set_processing(self, clip_id: str):
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE clips SET status='processing',updated_at=? WHERE id=? AND status='pending'",
                (utc_now(), clip_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Tác vụ không còn ở trạng thái chờ; không xuất trùng.")

    def finish_clip(self, clip_id: str, result: ExportResult):
        if result.status not in {"completed", "failed", "cancelled"}:
            raise ValueError("Trạng thái kết thúc không hợp lệ.")
        if result.status == "completed" and not result.output_path:
            raise ValueError("Clip hoàn tất phải có đường dẫn đầu ra.")
        fields = asdict(result)
        fields["updated_at"] = utc_now()
        with self.connection:
            self.connection.execute(
                "UPDATE clips SET " + ",".join(f"{key}=?" for key in fields) + " WHERE id=?",
                (*fields.values(), clip_id),
            )

    def clips(self, source_id=None, category=None, status=None, search="") -> list[dict]:
        query = "SELECT c.*,c.id AS clip_id,c.source_path_snapshot AS source_path,c.output_path AS clip_path,s.display_name,s.availability AS source_availability FROM clips c JOIN source_videos s ON s.id=c.source_video_id"
        conditions, values = [], []
        for field, value in (
            ("source_video_id", source_id),
            ("category", category),
            ("status", status),
        ):
            if value:
                conditions.append(f"c.{field}=?")
                values.append(value)
        if search:
            conditions.append(
                "(c.notes LIKE ? ESCAPE '\\' OR c.object_type LIKE ? ESCAPE '\\' OR s.display_name LIKE ? ESCAPE '\\' OR c.id LIKE ? ESCAPE '\\')"
            )
            term = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            values.extend([term] * 4)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        return [
            dict(row)
            for row in self.connection.execute(query + " ORDER BY c.created_at DESC", values)
        ]

    def get_setting(self, key: str, default=None):
        row = self.connection.execute(
            "SELECT value FROM app_settings WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except ValueError:
            return default

    def set_setting(self, key: str, value):
        with self.connection:
            self.connection.execute(
                "INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )

    def save_draft(self, source_id: str, draft: dict):
        with self.connection:
            self.connection.execute(
                "INSERT INTO drafts VALUES(?,?) ON CONFLICT(source_video_id) DO UPDATE SET draft_json=excluded.draft_json",
                (source_id, json.dumps(draft, ensure_ascii=False)),
            )

    def load_draft(self, source_id: str) -> dict:
        row = self.connection.execute(
            "SELECT draft_json FROM drafts WHERE source_video_id=?", (source_id,)
        ).fetchone()
        return json.loads(row[0]) if row else {}

    def recover_interrupted(self):
        with self.connection:
            self.connection.execute(
                "UPDATE clips SET status='failed',error_message=?,updated_at=? WHERE status IN ('pending','processing')",
                (
                    "Phiên trước bị gián đoạn. Chưa xác minh clip hoàn tất; có thể xuất lại bằng tác vụ mới.",
                    utc_now(),
                ),
            )

    def export_csv(self, path: Path, rows=None):
        path = Path(path).resolve()
        protected = {canonical_path(self.database.path)}
        protected.update(row["source_path"] for row in self.sources())
        all_clips = self.clips()
        protected.update(
            canonical_path(row["output_path"]) for row in all_clips if row["output_path"]
        )
        if canonical_path(path) in protected:
            raise ValueError("Không được ghi CSV lên video nguồn, clip hoặc database.")
        columns = [
            "clip_id",
            "source_video_id",
            "source_path",
            "clip_path",
            "requested_in_ms",
            "requested_out_ms",
            "event_start_ms",
            "event_end_ms",
            "actual_start_ms",
            "actual_duration_ms",
            "category",
            "object_type",
            "notes",
            "review_status",
            "cut_mode",
            "cut_precision",
            "status",
            "error_message",
            "created_at",
            "source_size_bytes",
            "source_mtime_ns",
        ]
        fd, temporary = tempfile.mkstemp(prefix=".vdt-csv-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(all_clips if rows is None else rows)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
