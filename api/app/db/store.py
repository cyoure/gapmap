"""PostgreSQL: 공고·갭 분석 결과·사용자 수정 상태. ORM 없이 SQL 그대로."""
import psycopg
from psycopg.types.json import Jsonb

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id           SERIAL PRIMARY KEY,
    company      TEXT,
    deadline     DATE,
    deadline_raw TEXT,
    posting      TEXT NOT NULL,           -- 사용자가 붙여넣은 공고 원문
    analysis     JSONB NOT NULL,          -- /jobs/analyze 결과 전체
    score        REAL,
    report       TEXT,                    -- 스트리밍이 끝난 뒤 저장
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 기술 단위로 펼쳐 저장 → Phase 4 통계(자주 요구되는 기술)를 SQL GROUP BY로 바로 계산
CREATE TABLE IF NOT EXISTS job_skills (
    job_id INT  NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    name   TEXT NOT NULL,
    kind   TEXT NOT NULL CHECK (kind IN ('required', 'preferred')),
    status TEXT NOT NULL CHECK (status IN ('보유', '근거 없음')),
    PRIMARY KEY (job_id, name)
);
-- 사용자가 직접 고친 상태. 자동 판정보다 항상 우선
CREATE TABLE IF NOT EXISTS skill_overrides (
    name       TEXT PRIMARY KEY,
    status     TEXT NOT NULL CHECK (status IN ('보유', '근거 없음')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _conn() -> psycopg.Connection:
    return psycopg.connect(config.DATABASE_URL, autocommit=True)


def init_schema() -> None:
    with _conn() as c:
        c.execute(SCHEMA)


def get_overrides() -> dict[str, str]:
    with _conn() as c:
        return dict(c.execute("SELECT name, status FROM skill_overrides").fetchall())


def set_override(name: str, status: str) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO skill_overrides (name, status) VALUES (%s, %s)
               ON CONFLICT (name) DO UPDATE SET status = EXCLUDED.status, updated_at = now()""",
            (name, status),
        )


def delete_override(name: str) -> bool:
    with _conn() as c:
        return c.execute("DELETE FROM skill_overrides WHERE name = %s", (name,)).rowcount > 0


def save_job(posting: str, analysis: dict, gaps: list[dict], score: float | None) -> int:
    """공고 + 기술별 상태를 한 트랜잭션으로 저장 (둘 중 하나만 들어가는 일이 없게)."""
    with _conn() as c, c.transaction():
        job_id = c.execute(
            """INSERT INTO jobs (company, deadline, deadline_raw, posting, analysis, score)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (analysis["company"], analysis["deadline"], analysis["deadline_raw"], posting, Jsonb(analysis), score),
        ).fetchone()[0]
        with c.cursor() as cur:
            cur.executemany(
                "INSERT INTO job_skills (job_id, name, kind, status) VALUES (%s, %s, %s, %s)",
                [(job_id, g["name"], g["kind"], g["status"]) for g in gaps],
            )
        return job_id


def save_report(job_id: int, report: str) -> None:
    with _conn() as c:
        c.execute("UPDATE jobs SET report = %s WHERE id = %s", (report, job_id))
