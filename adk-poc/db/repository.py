"""
DB-backed repository for skills and knowledge contributions.

Supports both PostgreSQL (psycopg) and Oracle (python-oracledb).
Set DB_TYPE=oracle and ORACLE_DSN to use Oracle; defaults to Postgres.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Optional


# ---- Configuration ----------------------------------------------------------

DB_TYPE = os.environ.get("DB_TYPE", "postgres")  # "postgres" or "oracle"


def _get_postgres_conn():
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(
        os.environ.get("DATABASE_URL", "postgresql://skills:skills@localhost:5432/skills"),
        row_factory=dict_row,
    )


def _get_oracle_conn():
    import oracledb
    return oracledb.connect(
        dsn=os.environ.get("ORACLE_DSN", "localhost:1521/FREEPDB1"),
        user=os.environ.get("ORACLE_USER", "skills"),
        password=os.environ.get("ORACLE_PASSWORD", "skills"),
    )


def get_conn():
    if DB_TYPE == "oracle":
        return _get_oracle_conn()
    return _get_postgres_conn()


# ---- SQL dialect adapter ----------------------------------------------------

class _SQL:
    """Adapts queries between Postgres and Oracle."""

    def __init__(self, db_type: str):
        self.is_oracle = db_type == "oracle"
        self.ph = ":" if self.is_oracle else "%"  # placeholder prefix

    def p(self, n: int) -> str:
        """Positional parameter placeholder."""
        return f":{n}" if self.is_oracle else "%s"

    @property
    def type_col(self) -> str:
        return "contribution_type" if self.is_oracle else "type"

    @property
    def metadata_col(self) -> str:
        return "metadata_json" if self.is_oracle else "metadata"

    @property
    def tags_col(self) -> str:
        return "tags_json" if self.is_oracle else "tags"

    @property
    def frontmatter_col(self) -> str:
        return "frontmatter_json" if self.is_oracle else "frontmatter"

    @property
    def files_col(self) -> str:
        return "files_json" if self.is_oracle else "files"

    def fts_where(self, param_idx: int) -> str:
        if self.is_oracle:
            return f"CONTAINS(v.content, :{param_idx}) > 0"
        return f"v.content_tsv @@ websearch_to_tsquery('english', %s)"

    def fts_rank(self, param_idx: int) -> str:
        if self.is_oracle:
            return f"SCORE({param_idx})"
        return f"ts_rank(v.content_tsv, websearch_to_tsquery('english', %s))"

    def tags_contains(self, param_idx: int) -> str:
        if self.is_oracle:
            return f"JSON_EXISTS({self.tags_col}, '$[*]?(@ == $tag)' PASSING :{param_idx} AS \"tag\")"
        return f"%s = ANY(c.tags)"

    def now(self) -> str:
        return "SYSTIMESTAMP" if self.is_oracle else "now()"


_sql = _SQL(DB_TYPE)


# ---- Data classes -----------------------------------------------------------

@dataclass
class Contribution:
    id: int
    type: str
    name: str
    domain: Optional[str]
    status: str
    current_version: int
    created_by: str
    tags: list[str]
    metadata: dict
    content: Optional[str] = None
    frontmatter: Optional[dict] = None
    files: Optional[dict] = None
    version: Optional[int] = None


@dataclass
class Approval:
    id: int
    contribution_id: int
    version: int
    decision: str
    decided_by: str
    reason: Optional[str]


# ---- Helpers ----------------------------------------------------------------

def _fetchone(cur) -> Optional[dict]:
    if DB_TYPE == "postgres":
        return cur.fetchone()
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0].lower() for d in cur.description]
    return dict(zip(cols, row))


def _fetchall(cur) -> list[dict]:
    if DB_TYPE == "postgres":
        return cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _exec(cur, sql: str, params=None):
    if DB_TYPE == "oracle" and params and isinstance(params, (list, tuple)):
        # Oracle wants named or positional :1, :2 — convert
        cur.execute(sql, params)
    else:
        cur.execute(sql, params)


def _json_str(val) -> str:
    if isinstance(val, str):
        return val
    return json.dumps(val)


def _parse_json(val) -> Any:
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        return json.loads(val)
    # Oracle CLOB
    if hasattr(val, 'read'):
        return json.loads(val.read())
    return json.loads(str(val))


# ---- Repository -------------------------------------------------------------

class ContributionRepository:

    def __init__(self, conn=None):
        self._conn = conn

    @property
    def conn(self):
        if self._conn is None or (hasattr(self._conn, 'closed') and self._conn.closed):
            self._conn = get_conn()
        return self._conn

    # -- Create ---------------------------------------------------------------

    def create(
        self,
        type: str,
        name: str,
        content: str,
        created_by: str,
        domain: Optional[str] = None,
        frontmatter: Optional[dict] = None,
        files: Optional[dict] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> Contribution:
        sha = hashlib.sha256(content.encode()).hexdigest()
        fm = json.dumps(frontmatter or {})
        f = json.dumps(files or {})
        t_val = tags or []
        m_val = metadata or {}

        cur = self.conn.cursor()

        if _sql.is_oracle:
            cur.execute(
                f"""INSERT INTO contributions ({_sql.type_col}, name, domain, created_by, {_sql.tags_col}, {_sql.metadata_col})
                    VALUES (:1, :2, :3, :4, :5, :6)""",
                (type, name, domain, created_by, json.dumps(t_val), json.dumps(m_val)),
            )
            cur.execute("SELECT id, status, current_version FROM contributions WHERE contribution_type = :1 AND name = :2",
                        (type, name))
        else:
            cur.execute(
                f"""INSERT INTO contributions (type, name, domain, created_by, tags, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, status, current_version""",
                (type, name, domain, created_by, t_val, json.dumps(m_val)),
            )

        row = _fetchone(cur)
        cid = row["id"]

        if _sql.is_oracle:
            cur.execute(
                f"""INSERT INTO contribution_versions
                    (contribution_id, version, content, {_sql.frontmatter_col}, {_sql.files_col}, content_sha256, created_by)
                    VALUES (:1, 1, :2, :3, :4, :5, :6)""",
                (cid, content, fm, f, sha, created_by),
            )
        else:
            cur.execute(
                """INSERT INTO contribution_versions
                    (contribution_id, version, content, frontmatter, files, content_sha256, created_by)
                    VALUES (%s, 1, %s, %s, %s, %s, %s)""",
                (cid, content, fm, f, sha, created_by),
            )

        self.conn.commit()
        cur.close()

        return Contribution(
            id=cid, type=type, name=name, domain=domain,
            status=row["status"], current_version=1,
            created_by=created_by, tags=t_val, metadata=m_val,
            content=content, frontmatter=frontmatter or {}, files=files or {}, version=1,
        )

    # -- Read -----------------------------------------------------------------

    def get_by_name(self, type: str, name: str) -> Optional[Contribution]:
        tc = _sql.type_col
        fc = _sql.frontmatter_col
        flc = _sql.files_col
        mc = _sql.metadata_col
        tgc = _sql.tags_col

        if _sql.is_oracle:
            q = f"""SELECT c.id, c.{tc} AS type, c.name, c.domain, c.status,
                           c.current_version, c.created_by, c.{tgc} AS tags, c.{mc} AS metadata,
                           v.version, v.content, v.{fc} AS frontmatter, v.{flc} AS files
                    FROM contributions c
                    JOIN contribution_versions v ON v.contribution_id = c.id AND v.version = c.current_version
                    WHERE c.{tc} = :1 AND c.name = :2"""
        else:
            q = f"""SELECT c.*, v.version, v.content, v.frontmatter, v.files
                    FROM contributions c
                    JOIN contribution_versions v ON v.contribution_id = c.id AND v.version = c.current_version
                    WHERE c.type = %s AND c.name = %s"""

        cur = self.conn.cursor()
        cur.execute(q, (type, name))
        row = _fetchone(cur)
        cur.close()
        return self._row_to_contribution(row) if row else None

    def get_by_id(self, contribution_id: int) -> Optional[Contribution]:
        tc = _sql.type_col
        fc = _sql.frontmatter_col
        flc = _sql.files_col
        mc = _sql.metadata_col
        tgc = _sql.tags_col

        if _sql.is_oracle:
            q = f"""SELECT c.id, c.{tc} AS type, c.name, c.domain, c.status,
                           c.current_version, c.created_by, c.{tgc} AS tags, c.{mc} AS metadata,
                           v.version, v.content, v.{fc} AS frontmatter, v.{flc} AS files
                    FROM contributions c
                    JOIN contribution_versions v ON v.contribution_id = c.id AND v.version = c.current_version
                    WHERE c.id = :1"""
        else:
            q = """SELECT c.*, v.version, v.content, v.frontmatter, v.files
                   FROM contributions c
                   JOIN contribution_versions v ON v.contribution_id = c.id AND v.version = c.current_version
                   WHERE c.id = %s"""

        cur = self.conn.cursor()
        cur.execute(q, (contribution_id,))
        row = _fetchone(cur)
        cur.close()
        return self._row_to_contribution(row) if row else None

    def list_contributions(
        self,
        type: Optional[str] = None,
        status: Optional[str] = None,
        domain: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> list[Contribution]:
        tc = _sql.type_col
        fc = _sql.frontmatter_col
        flc = _sql.files_col
        mc = _sql.metadata_col
        tgc = _sql.tags_col

        clauses = []
        params: list = []
        idx = 1

        if type:
            clauses.append(f"c.{tc} = :{idx}" if _sql.is_oracle else f"c.type = %s")
            params.append(type)
            idx += 1
        if status:
            clauses.append(f"c.status = :{idx}" if _sql.is_oracle else "c.status = %s")
            params.append(status)
            idx += 1
        if domain:
            clauses.append(f"c.domain = :{idx}" if _sql.is_oracle else "c.domain = %s")
            params.append(domain)
            idx += 1
        if tag:
            clauses.append(_sql.tags_contains(idx))
            params.append(tag)
            idx += 1

        where = "WHERE " + " AND ".join(clauses) if clauses else ""

        if _sql.is_oracle:
            q = f"""SELECT c.id, c.{tc} AS type, c.name, c.domain, c.status,
                           c.current_version, c.created_by, c.{tgc} AS tags, c.{mc} AS metadata,
                           v.version, v.content, v.{fc} AS frontmatter, v.{flc} AS files
                    FROM contributions c
                    JOIN contribution_versions v ON v.contribution_id = c.id AND v.version = c.current_version
                    {where}
                    ORDER BY c.updated_at DESC"""
        else:
            q = f"""SELECT c.*, v.version, v.content, v.frontmatter, v.files
                    FROM contributions c
                    JOIN contribution_versions v ON v.contribution_id = c.id AND v.version = c.current_version
                    {where}
                    ORDER BY c.updated_at DESC"""

        cur = self.conn.cursor()
        cur.execute(q, params)
        rows = _fetchall(cur)
        cur.close()
        return [self._row_to_contribution(r) for r in rows]

    # -- Search ---------------------------------------------------------------

    def search(self, query: str, type: Optional[str] = None) -> list[Contribution]:
        tc = _sql.type_col
        fc = _sql.frontmatter_col
        flc = _sql.files_col
        mc = _sql.metadata_col
        tgc = _sql.tags_col

        params: list = []
        idx = 1

        if _sql.is_oracle:
            # Oracle Text CONTAINS
            fts_clause = f"CONTAINS(v.content, :{idx}, 1) > 0"
            rank_expr = "SCORE(1)"
            params.append(query)
            idx += 1

            clauses = [fts_clause, "c.status = 'approved'", "v.version = c.current_version"]
            if type:
                clauses.append(f"c.{tc} = :{idx}")
                params.append(type)
                idx += 1

            where = "WHERE " + " AND ".join(clauses)
            q = f"""SELECT c.id, c.{tc} AS type, c.name, c.domain, c.status,
                           c.current_version, c.created_by, c.{tgc} AS tags, c.{mc} AS metadata,
                           v.version, v.content, v.{fc} AS frontmatter, v.{flc} AS files,
                           {rank_expr} AS rank
                    FROM contributions c
                    JOIN contribution_versions v ON v.contribution_id = c.id
                    {where}
                    ORDER BY rank DESC
                    FETCH FIRST 10 ROWS ONLY"""
        else:
            params.append(query)  # for rank
            params.append(query)  # for where
            clauses = [
                "v.content_tsv @@ websearch_to_tsquery('english', %s)",
                "c.status = 'approved'",
                "v.version = c.current_version",
            ]
            if type:
                clauses.append("c.type = %s")
                params.append(type)

            where = "WHERE " + " AND ".join(clauses)
            q = f"""SELECT c.*, v.version, v.content, v.frontmatter, v.files,
                           ts_rank(v.content_tsv, websearch_to_tsquery('english', %s)) AS rank
                    FROM contributions c
                    JOIN contribution_versions v ON v.contribution_id = c.id
                    {where}
                    ORDER BY rank DESC
                    LIMIT 10"""

        cur = self.conn.cursor()
        cur.execute(q, params)
        rows = _fetchall(cur)
        cur.close()
        return [self._row_to_contribution(r) for r in rows]

    # -- Update (new version) -------------------------------------------------

    def update_content(
        self,
        contribution_id: int,
        content: str,
        updated_by: str,
        frontmatter: Optional[dict] = None,
        files: Optional[dict] = None,
        change_summary: Optional[str] = None,
    ) -> Contribution:
        sha = hashlib.sha256(content.encode()).hexdigest()
        fc = _sql.frontmatter_col
        flc = _sql.files_col

        cur = self.conn.cursor()

        if _sql.is_oracle:
            cur.execute("SELECT current_version FROM contributions WHERE id = :1", (contribution_id,))
        else:
            cur.execute("SELECT current_version FROM contributions WHERE id = %s", (contribution_id,))

        row = _fetchone(cur)
        if not row:
            cur.close()
            raise ValueError(f"Contribution {contribution_id} not found")

        new_version = row["current_version"] + 1

        if frontmatter is None or files is None:
            if _sql.is_oracle:
                cur.execute(f"SELECT {fc} AS frontmatter, {flc} AS files FROM contribution_versions WHERE contribution_id = :1 AND version = :2",
                            (contribution_id, row["current_version"]))
            else:
                cur.execute("SELECT frontmatter, files FROM contribution_versions WHERE contribution_id = %s AND version = %s",
                            (contribution_id, row["current_version"]))
            prev = _fetchone(cur)
            if frontmatter is None:
                frontmatter = _parse_json(prev["frontmatter"]) if prev else {}
            if files is None:
                files = _parse_json(prev["files"]) if prev else {}

        fm_str = json.dumps(frontmatter)
        f_str = json.dumps(files)

        if _sql.is_oracle:
            cur.execute(
                f"""INSERT INTO contribution_versions
                    (contribution_id, version, content, {fc}, {flc}, content_sha256, created_by, change_summary)
                    VALUES (:1, :2, :3, :4, :5, :6, :7, :8)""",
                (contribution_id, new_version, content, fm_str, f_str, sha, updated_by, change_summary),
            )
            cur.execute(
                f"UPDATE contributions SET current_version = :1, updated_at = SYSTIMESTAMP, status = 'pending_review' WHERE id = :2",
                (new_version, contribution_id),
            )
        else:
            cur.execute(
                """INSERT INTO contribution_versions
                    (contribution_id, version, content, frontmatter, files, content_sha256, created_by, change_summary)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (contribution_id, new_version, content, fm_str, f_str, sha, updated_by, change_summary),
            )
            cur.execute(
                "UPDATE contributions SET current_version = %s, updated_at = now(), status = 'pending_review' WHERE id = %s",
                (new_version, contribution_id),
            )

        self.conn.commit()
        cur.close()
        return self.get_by_id(contribution_id)

    # -- Submit for review ----------------------------------------------------

    def submit_for_review(self, contribution_id: int) -> Contribution:
        cur = self.conn.cursor()
        if _sql.is_oracle:
            cur.execute(
                "UPDATE contributions SET status = 'pending_review', updated_at = SYSTIMESTAMP WHERE id = :1 AND status = 'draft'",
                (contribution_id,),
            )
        else:
            cur.execute(
                "UPDATE contributions SET status = 'pending_review', updated_at = now() WHERE id = %s AND status = 'draft' RETURNING id",
                (contribution_id,),
            )
        self.conn.commit()
        cur.close()
        result = self.get_by_id(contribution_id)
        if not result or result.status not in ('pending_review', 'approved'):
            raise ValueError(f"Contribution {contribution_id} not found or not in draft status")
        return result

    # -- Approve / Reject -----------------------------------------------------

    def approve(self, contribution_id: int, version: int, decided_by: str, reason: str = "") -> Approval:
        cur = self.conn.cursor()
        if _sql.is_oracle:
            cur.execute(
                "UPDATE contributions SET status = 'approved', updated_at = SYSTIMESTAMP WHERE id = :1 AND current_version = :2",
                (contribution_id, version),
            )
            cur.execute(
                """INSERT INTO approvals (contribution_id, version, decision, decided_by, reason)
                   VALUES (:1, :2, 'approved', :3, :4)""",
                (contribution_id, version, decided_by, reason),
            )
            cur.execute("SELECT id FROM approvals WHERE contribution_id = :1 AND version = :2 AND decision = 'approved' ORDER BY id DESC FETCH FIRST 1 ROW ONLY",
                        (contribution_id, version))
        else:
            cur.execute(
                "UPDATE contributions SET status = 'approved', updated_at = now() WHERE id = %s AND current_version = %s RETURNING id",
                (contribution_id, version),
            )
            cur.execute(
                """INSERT INTO approvals (contribution_id, version, decision, decided_by, reason)
                   VALUES (%s, %s, 'approved', %s, %s) RETURNING id""",
                (contribution_id, version, decided_by, reason),
            )

        row = _fetchone(cur)
        self.conn.commit()
        cur.close()

        return Approval(
            id=row["id"], contribution_id=contribution_id,
            version=version, decision="approved",
            decided_by=decided_by, reason=reason,
        )

    def reject(self, contribution_id: int, version: int, decided_by: str, reason: str) -> Approval:
        cur = self.conn.cursor()
        if _sql.is_oracle:
            cur.execute(
                "UPDATE contributions SET status = 'rejected', updated_at = SYSTIMESTAMP WHERE id = :1 AND current_version = :2",
                (contribution_id, version),
            )
            cur.execute(
                """INSERT INTO approvals (contribution_id, version, decision, decided_by, reason)
                   VALUES (:1, :2, 'rejected', :3, :4)""",
                (contribution_id, version, decided_by, reason),
            )
            cur.execute("SELECT id FROM approvals WHERE contribution_id = :1 AND version = :2 AND decision = 'rejected' ORDER BY id DESC FETCH FIRST 1 ROW ONLY",
                        (contribution_id, version))
        else:
            cur.execute(
                "UPDATE contributions SET status = 'rejected', updated_at = now() WHERE id = %s AND current_version = %s RETURNING id",
                (contribution_id, version),
            )
            cur.execute(
                """INSERT INTO approvals (contribution_id, version, decision, decided_by, reason)
                   VALUES (%s, %s, 'rejected', %s, %s) RETURNING id""",
                (contribution_id, version, decided_by, reason),
            )

        row = _fetchone(cur)
        self.conn.commit()
        cur.close()

        return Approval(
            id=row["id"], contribution_id=contribution_id,
            version=version, decision="rejected",
            decided_by=decided_by, reason=reason,
        )

    # -- Version history ------------------------------------------------------

    def get_version_history(self, contribution_id: int) -> list[dict]:
        if _sql.is_oracle:
            q = """SELECT v.version, v.created_by, v.created_at, v.change_summary, v.content_sha256,
                          a.decision, a.decided_by, a.reason AS approval_reason, a.decided_at
                   FROM contribution_versions v
                   LEFT JOIN approvals a ON a.contribution_id = v.contribution_id AND a.version = v.version
                   WHERE v.contribution_id = :1
                   ORDER BY v.version DESC"""
        else:
            q = """SELECT v.version, v.created_by, v.created_at, v.change_summary, v.content_sha256,
                          a.decision, a.decided_by, a.reason AS approval_reason, a.decided_at
                   FROM contribution_versions v
                   LEFT JOIN approvals a ON a.contribution_id = v.contribution_id AND a.version = v.version
                   WHERE v.contribution_id = %s
                   ORDER BY v.version DESC"""

        cur = self.conn.cursor()
        cur.execute(q, (contribution_id,))
        rows = _fetchall(cur)
        cur.close()
        return rows

    # -- Archive --------------------------------------------------------------

    def archive(self, contribution_id: int) -> Contribution:
        cur = self.conn.cursor()
        if _sql.is_oracle:
            cur.execute("UPDATE contributions SET status = 'archived', updated_at = SYSTIMESTAMP WHERE id = :1", (contribution_id,))
        else:
            cur.execute("UPDATE contributions SET status = 'archived', updated_at = now() WHERE id = %s RETURNING id", (contribution_id,))
        self.conn.commit()
        cur.close()
        return self.get_by_id(contribution_id)

    # -- Internal -------------------------------------------------------------

    def _row_to_contribution(self, row: dict) -> Contribution:
        return Contribution(
            id=row["id"],
            type=row.get("type") or row.get("contribution_type", ""),
            name=row["name"],
            domain=row.get("domain"),
            status=row["status"],
            current_version=row["current_version"],
            created_by=row["created_by"],
            tags=_parse_json(row.get("tags", "[]")),
            metadata=_parse_json(row.get("metadata", "{}")),
            content=row.get("content"),
            frontmatter=_parse_json(row.get("frontmatter", "{}")),
            files=_parse_json(row.get("files", "{}")),
            version=row.get("version"),
        )
