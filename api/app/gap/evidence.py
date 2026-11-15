"""기술별 상태 판정. 판정은 규칙(기술명이 이력서에 실제로 있나), RAG 검색은 '참고 힌트'로만."""
import re

from app.gap.schema import HAVE, NO_EVIDENCE, SkillGap
from app.jobs.normalize import dictionary
from app.jobs.schema import JobAnalysis
from app.rag import store

# 이 유사도 이상인 문단만 힌트로 보여준다. 샘플 이력서 측정값(2026-11-18):
# 관련 있는 문단 CI/CD→배포 자동화 0.498, 무관한 문단 최고 0.416 → 그 사이
HINT_THRESHOLD = 0.45
SNIPPET = 40  # 근거 문장 앞뒤로 보여줄 글자 수


def _pattern(name: str) -> re.Pattern:
    """'Spring Boot' → SpringBoot, spring-boot, Spring.Boot 모두 매칭.
    영문 앞뒤 경계를 둬서 'Java'가 'JavaScript'에, 'Go'가 'Google'에 걸리지 않게 한다.
    (한글 뒤의 조사는 허용: 'JPA로', '스프링부트를' / 뒤에 붙은 버전 숫자도 허용: 'Java8', 'C++17')"""
    parts = [re.escape(p) for p in re.split(r"[\s.\-/]+", name.strip()) if p]
    return re.compile(r"(?<![A-Za-z0-9])" + r"[\s.\-/]?".join(parts) + r"(?!\d*[A-Za-z])", re.I)


def _snippet(text: str, m: re.Match) -> str:
    s = text[max(0, m.start() - SNIPPET) : m.end() + SNIPPET]
    return "…" + re.sub(r"\s+", " ", s).strip() + "…"


def _find(names: list[str], chunks: list[dict]) -> tuple[str, str] | None:
    """기술명·동의어 중 하나라도 이력서에 있으면 (근거 문장, 파일명)."""
    patterns = [_pattern(n) for n in names]
    for ch in chunks:
        for p in patterns:
            if m := p.search(ch["text"]):
                return _snippet(ch["text"], m), ch["source"]
    return None


def find_gaps(analysis: JobAnalysis, overrides: dict[str, str]) -> list[SkillGap]:
    skills = [(s.name, "required") for s in analysis.required] + [(s.name, "preferred") for s in analysis.preferred]
    if not skills:
        return []

    words = dictionary()
    chunks = store.all_chunks()
    # RAG: 기술명+동의어로 의미 검색 (예: "CI/CD 지속적 통합 …" → 배포 자동화 문단)
    nearest = store.nearest_many([" ".join([n, *words.get(n, [])]) for n, _ in skills])

    gaps = []
    for (name, kind), near in zip(skills, nearest):
        if name in overrides:  # 사용자가 직접 고친 상태가 항상 우선
            gaps.append(SkillGap(name=name, kind=kind, status=overrides[name], source="user"))
        elif found := _find([name, *words.get(name, [])], chunks):
            gaps.append(SkillGap(name=name, kind=kind, status=HAVE, source="resume",
                                 evidence=found[0], evidence_file=found[1]))
        else:
            hint = near["score"] >= HINT_THRESHOLD
            gaps.append(SkillGap(name=name, kind=kind, status=NO_EVIDENCE, source="resume",
                                 hint=re.sub(r"\s+", " ", near["text"])[:80] + "…" if hint else None,
                                 hint_score=near["score"] if hint else None))
    return gaps
