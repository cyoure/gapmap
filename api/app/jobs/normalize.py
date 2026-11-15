"""기술명 정규화: ① skills.yaml 사전 → ② 없으면 Chroma `skills` 컬렉션에서 임베딩 유사도."""
import hashlib
import re
from pathlib import Path

import yaml

from app.chroma import client
from app.jobs.schema import Skill
from app.llm import embedder

SKILLS_FILE = Path(__file__).with_name("skills.yaml")
COLLECTION = "skills"
# 이 유사도 이상일 때만 사전의 기술로 인정. bge-m3 측정값(2026-11-18):
# 무관한 기술 최고 0.663(Excel), 올바른 매칭 최저 0.751(Kafka Streams) → 그 사이
THRESHOLD = 0.75


def _key(name: str) -> str:
    """비교용 키: 대소문자·공백·점·하이픈·슬래시·밑줄 무시."""
    return re.sub(r"[\s./\-_]", "", name).lower()


def _dict_match(raw: str, lookup: dict) -> str | None:
    """사전 매칭. 실패하면 끝의 버전 숫자를 떼고 한 번 더 (SpringBoot3 → springboot, Java 17 → java)."""
    key = _key(raw)
    return lookup.get(key) or lookup.get(re.sub(r"\d+$", "", key))


# LLM이 덜 다듬은 표기의 꼬리말: "CI/CD 구성 경험" → "CI/CD"
_FILLER = re.compile(r"(\s*(사용|활용|구성|설계|개발|운영|도입|구축|경험|능력|이해|지식|역량|기반|환경))+$")
# 여러 기술이 묶인 표기: "MySQL/PostgreSQL", "Go or Java"
_SPLIT = re.compile(r"\s*(?:/|,|·|&|\s또는\s|\sor\s|\sand\s)\s*", re.I)


def _candidates(raw: str, lookup: dict) -> list[str]:
    """원문 한 항목 → 매칭해볼 기술명 후보들. 괄호 내용·꼬리말 제거 후, 사전에 없으면 쪼갠다."""
    s = _FILLER.sub("", re.sub(r"\(.*?\)", "", raw)).strip() or raw.strip()
    if _dict_match(s, lookup):  # CI/CD처럼 "/"가 있어도 사전에 있으면 그대로
        return [s]
    parts = [p for p in _SPLIT.split(s) if p.strip()]
    return parts if len(parts) > 1 else [s]


def _load() -> tuple[dict, dict, str]:
    """요청마다 다시 읽는다 → skills.yaml을 고치면 재시작 없이 반영."""
    text = SKILLS_FILE.read_text(encoding="utf-8")
    data = yaml.safe_load(text)  # {표준이름: [동의어...]}
    lookup = {_key(n): canon for canon, aliases in data.items() for n in [canon, *(aliases or [])]}
    return data, lookup, hashlib.md5(text.encode()).hexdigest()


def _collection(data: dict, version: str):
    """사전 내용(해시)이 바뀌었을 때만 임베딩을 다시 만든다. 그 외에는 Chroma에 저장된 벡터 재사용."""
    c = client()
    try:
        col = c.get_collection(COLLECTION)
        if (col.metadata or {}).get("version") == version:
            return col
        c.delete_collection(COLLECTION)
    except Exception:  # 컬렉션이 아직 없음
        pass

    names = [(n, canon) for canon, aliases in data.items() for n in [canon, *(aliases or [])]]
    col = c.create_collection(COLLECTION, metadata={"hnsw:space": "cosine", "version": version})
    col.add(
        ids=[str(i) for i in range(len(names))],
        documents=[n for n, _ in names],
        embeddings=embedder.embed_documents([n for n, _ in names]),
        metadatas=[{"canonical": canon} for _, canon in names],
    )
    return col


def normalize(raws: list[str]) -> list[Skill]:
    data, lookup, version = _load()
    skills: list[Skill | None] = []
    unknown: list[tuple[int, str, str]] = []  # (자리, 원문, 후보)

    for raw in (r.strip() for r in raws if r and r.strip()):
        for cand in _candidates(raw, lookup):
            if canon := _dict_match(cand, lookup):
                skills.append(Skill(name=canon, raw=raw, match="dict"))
            else:
                unknown.append((len(skills), raw, cand))
                skills.append(None)  # 자리만 잡아두고 아래에서 채움 (원래 순서 유지)

    if unknown:
        col = _collection(data, version)
        res = col.query(query_embeddings=embedder.embed_documents([c for *_, c in unknown]), n_results=1)
        for (i, raw, cand), metas, dists in zip(unknown, res["metadatas"], res["distances"]):
            score = round(1 - dists[0], 3)
            if score >= THRESHOLD:
                skills[i] = Skill(name=metas[0]["canonical"], raw=raw, match="embedding", score=score)
            else:  # 사전에 없는 새 기술 → 다듬은 이름 그대로 유지
                skills[i] = Skill(name=cand, raw=raw, match="none", score=score)

    # 정규화 후 같은 이름이 된 항목은 하나만 (예: "Spring Boot", "스프링부트")
    seen, result = set(), []
    for s in skills:
        if s and s.name not in seen:
            seen.add(s.name)
            result.append(s)
    return result


def dictionary() -> dict[str, list[str]]:
    """{표준이름: [동의어...]} — 갭 분석에서 이력서 근거를 찾을 때 동의어까지 확인하려고 사용."""
    return {canon: list(aliases or []) for canon, aliases in _load()[0].items()}


def canonical(name: str) -> str:
    """사용자가 입력한 기술명을 표준 이름으로 (PATCH /skills/스프링부트 → Spring Boot). 사전에 없으면 그대로."""
    return _dict_match(name, _load()[1]) or name.strip()
