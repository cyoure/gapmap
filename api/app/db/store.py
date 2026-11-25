"""PostgreSQL: 공고·갭 분석 결과·사용자 수정 상태. ORM 없이 SQL 그대로."""
from datetime import date

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
-- 사용자가 "기술이 아님"으로 숨긴 이름 (OCR 잡음·자격증 등). 행을 지우지 않고 숨겨서 되돌릴 수 있게
CREATE TABLE IF NOT EXISTS hidden_skills (
    name      TEXT PRIMARY KEY,
    hidden_at TIMESTAMPTZ NOT NULL DEFAULT now()
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


def hidden_skills() -> list[str]:
    with _conn() as c:
        return [r[0] for r in c.execute("SELECT name FROM hidden_skills ORDER BY name").fetchall()]


def hide_skill(name: str) -> None:
    with _conn() as c:
        c.execute("INSERT INTO hidden_skills (name) VALUES (%s) ON CONFLICT DO NOTHING", (name,))


def unhide_skill(name: str) -> bool:
    with _conn() as c:
        return c.execute("DELETE FROM hidden_skills WHERE name = %s", (name,)).rowcount > 0


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


STATS_SQL = """
SELECT s.name,
       count(DISTINCT md5(j.posting))                                  AS jobs,      -- 이 기술을 요구한 공고 수
       count(DISTINCT md5(j.posting)) FILTER (WHERE s.kind = 'required') AS required,  -- 그중 필수로 요구
       coalesce(o.status, (array_agg(s.status ORDER BY j.created_at DESC))[1]) AS my_status  -- 직접 수정 > 최근 판정
FROM job_skills s
JOIN jobs j ON j.id = s.job_id
LEFT JOIN skill_overrides o ON o.name = s.name
WHERE s.name NOT IN (SELECT name FROM hidden_skills)               -- 사용자가 숨긴 항목 제외
GROUP BY s.name, o.status
ORDER BY jobs DESC, required DESC, s.name
LIMIT %s
"""


def stats(limit: int) -> dict:
    """저장된 공고에서 자주 요구되는 기술 순위. 같은 공고를 여러 번 분석해도 한 번으로 센다(md5)."""
    with _conn() as c:
        total = c.execute("SELECT count(DISTINCT md5(posting)) FROM jobs").fetchone()[0]
        rows = c.execute(STATS_SQL, (limit,)).fetchall()
    return {
        "total_jobs": total,
        "hidden": hidden_skills(),
        "skills": [
            {"name": n, "jobs": cnt, "required": req, "percent": round(100 * cnt / total, 1), "my_status": st}
            for n, cnt, req, st in rows
        ],
    }


UPCOMING_SQL = """
SELECT * FROM (
    SELECT DISTINCT ON (md5(j.posting))            -- 같은 공고를 여러 번 분석했으면 최신 분석 1건만
           j.company, j.deadline, j.score,
           array(SELECT s.name FROM job_skills s
                 LEFT JOIN skill_overrides o ON o.name = s.name
                 WHERE s.job_id = j.id AND s.kind = 'required'
                   AND coalesce(o.status, s.status) = '근거 없음'   -- 직접 수정 > 자동 판정
                   AND s.name NOT IN (SELECT name FROM hidden_skills)
                 ORDER BY s.name) AS missing
    FROM jobs j
    WHERE j.deadline BETWEEN %s AND %s
    ORDER BY md5(j.posting), j.created_at DESC
) t
ORDER BY deadline, company
"""


def upcoming_jobs(start: date, end: date) -> list[dict]:
    """마감일이 start~end(포함)인 공고. D-day 계산은 여기서 하지 않는다 (calc_dday 함수 담당)."""
    with _conn() as c:
        rows = c.execute(UPCOMING_SQL, (start, end)).fetchall()
    return [{"company": co, "deadline": d, "score": s, "missing": m} for co, d, s, m in rows]


def count_jobs_since(days: int) -> int:
    """최근 days일 동안 분석한 공고 수 (같은 공고 중복 제외)."""
    with _conn() as c:
        return c.execute(
            "SELECT count(DISTINCT md5(posting)) FROM jobs WHERE created_at >= now() - make_interval(days => %s)",
            (days,),
        ).fetchone()[0]
