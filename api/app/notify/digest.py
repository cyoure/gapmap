"""n8n이 호출하는 알림 데이터 + Discord 문구.

D-day는 calc_dday 함수로 계산하고 문구도 여기서 만든다. n8n은 일정에 맞춰 호출하고 전달만 한다.
"""
from datetime import timedelta

from app.db import store as db
from app.gap.score import calc_dday
from app.jobs.service import today_kst

DISCORD_LIMIT = 2000  # Discord 메시지 최대 길이


def _clip(text: str) -> str:
    return text if len(text) <= DISCORD_LIMIT else text[: DISCORD_LIMIT - 1] + "…"


def _upcoming(days: int) -> list[dict]:
    today = today_kst()
    jobs = db.upcoming_jobs(today, today + timedelta(days=days))
    return [{**j, "dday": calc_dday(j["deadline"], today), "deadline": j["deadline"].isoformat()} for j in jobs]


def _line(j: dict) -> str:
    dday = "오늘 마감" if j["dday"] == 0 else f"D-{j['dday']}"
    score = f"{j['score']:.0f}점" if j["score"] is not None else "점수 없음"
    missing = ", ".join(j["missing"]) or "없음"
    return f"- **{j['company'] or '회사명 없음'}** {dday} ({j['deadline']}) · 매칭 {score} · 필수 중 근거 없음: {missing}"


def deadline_alert(days: int) -> dict:
    """마감이 오늘~days일 뒤인 공고. count가 0이면 n8n이 보내지 않는다."""
    jobs = _upcoming(days)
    message = "⏰ **마감 임박 공고**\n" + "\n".join(map(_line, jobs)) if jobs else ""
    return {"count": len(jobs), "jobs": jobs, "message": _clip(message)}


def weekly_summary() -> dict:
    """최근 7일 분석 공고 수, 다음 7일 마감, 자주 요구되는 기술 Top 5."""
    added = db.count_jobs_since(7)
    upcoming = _upcoming(7)
    stats = db.stats(5)

    lines = [
        f"📊 **GapMap 주간 요약** ({today_kst().isoformat()})",
        f"- 이번 주 분석한 공고: {added}개 (누적 {stats['total_jobs']}개)",
        f"- 다음 7일 안에 마감: {len(upcoming)}개",
        *[f"  {_line(j)}" for j in upcoming],
    ]
    if stats["skills"]:
        lines.append("- 자주 요구되는 기술 Top 5")
        lines += [
            f"  {i}. {s['name']} — {s['jobs']}개 공고({s['percent']}%) · 내 상태: {s['my_status']}"
            for i, s in enumerate(stats["skills"], 1)
        ]
    return {"added": added, "upcoming": upcoming, "top_skills": stats["skills"], "message": _clip("\n".join(lines))}
