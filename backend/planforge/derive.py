# -*- coding: utf-8 -*-
"""파생물 생성 오케스트레이터 (make-ppt·make-doc 이식).

LLM/코드 역할 분리:
- 결정론(코드): 문서 필터·골격 검증·스키마 검증(builder.validate)·numcheck 측정·
  파일 기록·빌더 실행·채번.
- LLM: plan 표기 → slides.json/report.json 콘텐츠 변환 (도구 호출 1회). 스키마 위반만
  재변환 요청 (최대 N회). 수치 무결성은 스키마 통과 후 1회 측정해 findings로 보고한다 —
  게이트·재시도는 하지 않는다(판정 권위는 검수 단계, 결정 17).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .llm.loops import run_tool_loop
from .numcheck import Finding, check_report, check_slides
from .plan import Plan, PlanError, filter_slides, parse_plan_file, validate_skeleton

PROMPTS_DIR = Path(__file__).parent / "llm" / "prompts"
MAX_ATTEMPTS = 3
UNCONFIRMED_MARK = "(미확정"

SLIDES_TOOL = {
    "type": "function",
    "function": {
        "name": "write_slides_json",
        "description": "변환 완료된 slides.json 객체 전체를 전달한다 (정확히 1회 호출)",
        "parameters": {
            "type": "object",
            "properties": {
                "meta": {"type": "object"},
                "slides": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["meta", "slides"],
        },
    },
}

REPORT_TOOL = {
    "type": "function",
    "function": {
        "name": "write_report_json",
        "description": "변환 완료된 report.json 객체 전체를 전달한다 (정확히 1회 호출)",
        "parameters": {
            "type": "object",
            "properties": {
                "meta": {"type": "object"},
                "sections": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["meta", "sections"],
        },
    },
}


class DeriveError(ValueError):
    """파생물 생성 실패 (LLM이 도구 호출 없이 소진). 수치 위반은 실패가 아니라 numcheck
    측정 기록이며 판정은 검수 단계가 한다(결정 17) — 스키마 위반 지속은 하위형."""


class DeriveSchemaError(DeriveError):
    """파생물 생성 실패 — LLM 결과가 스키마 검증(builder.validate)을 반복 통과하지 못함.

    소진 오류에 실제 실패 종류를 라벨링하기 위한 하위형 — worker가
    JobErrorClass.SCHEMA로 분류한다. isinstance(e, DeriveError) 계약은 유지:
    기존 catch 사이트(워커·CLI)는 하위 호환.
    """


@dataclass
class DeriveResult:
    work_path: Path
    slides_count: int = 0
    sections_count: int = 0
    unconfirmed: list[int] = field(default_factory=list)  # (미확정) 표기가 남은 슬라이드 번호
    findings: list[Finding] = field(default_factory=list)   # numcheck 측정값 — 게이트 아님, 판정은 검수 (결정 17)
    attempts: int = 1


# ---------------------------------------------------------------- plan 직렬화 (LLM 입력)

def render_slides_text(plan: Plan, slides, doc: str) -> str:
    """필터된 슬라이드를 plan 표기 그대로 직렬화한다 (콘텐츠 무변경)."""
    out = [
        f"# {plan.title}",
        "- 산출 문서(대상): " + doc,
        f"- 목적: {plan.purpose}",
        f"- 청중: {plan.audience}",
        f"- 예상 분량: {plan.length}",
        "## 핵심 메시지 (3개)",
    ]
    for i, km in enumerate(plan.key_messages, 1):
        out.append(f"{i}. {km}")
    out.append("## 슬라이드 목록 (대상 문서로 필터됨 — 이 순서 그대로)")
    for s in slides:
        out.append(f"### {s.no}. [유형: {_type_ko(s.type)}] {s.title}")
        if s.message:
            out.append(f"- 핵심문장: {s.message}")
        for col, tag in ((s.left, "좌"), (s.right, "우")):
            if col is not None:
                out.append(f"- {tag} ({col.heading}):")
                for b in col.bullets:
                    label = f"{b.label} | " if b.label else ""
                    out.append(f"  - {label}{b.body}")
        if s.table is not None:
            out.append("- 표: [" + " | ".join(s.table.headers) + "]")
            for row in s.table.rows:
                out.append("  - " + " | ".join(str(c) for c in row))
        if s.chart is not None:
            out.append("- 차트:")
            out.append("  - 범주: " + ", ".join(s.chart.categories))
            for sr in s.chart.series:
                out.append("  - " + sr.name + " | " + ", ".join(_fmt_plan_value(v) for v in sr.values))
        if s.arch:
            out.append("- 구성:")
        for g in s.arch:
            out.append(f"  - {g.name} | " + ", ".join(g.items))
        if s.source:
            out.append(f"- 근거/출처: {s.source}")
    return "\n".join(out)


def _fmt_plan_value(v) -> str:
    """plan 표기 그대로 (파서가 원문 표기를 보존 — 수치 무결성 기준)."""
    return str(v)


def _type_ko(t: str) -> str:
    return {"cover": "표지", "toc": "목차", "two-col": "2단", "table": "표",
            "chart": "차트", "arch": "구성", "closing": "마무리"}[t]


# ---------------------------------------------------------------- Deriver

class Deriver:
    """chat_fn(messages, tools) -> {"content", "tool_calls"} 주입받아 파생물을 생성한다."""

    def __init__(self, chat_fn, workspace: str | Path, max_attempts: int = MAX_ATTEMPTS):
        self.chat_fn = chat_fn
        self.workspace = Path(workspace)
        self.max_attempts = max_attempts

    # ---- 공용 절차

    def _prepare(self, plan_path: str | Path, doc: str | None):
        plan = parse_plan_file(plan_path)
        doc = doc or plan.docs[0]
        if doc not in plan.docs:
            raise PlanError(f"문서 '{doc}'가 plan 메타 '산출 문서'({', '.join(plan.docs)})에 없습니다")
        slides = filter_slides(plan.slides, doc)
        validate_skeleton(slides)  # 원칙 8 — 미달 시 중단
        unconfirmed = [s.no for s in slides if UNCONFIRMED_MARK in (s.source or "") or UNCONFIRMED_MARK in (s.message or "")]
        return plan, doc, slides, unconfirmed

    def _system_prompt(self, kind: str) -> str:
        fname = "derive_slides.md" if kind == "slides" else "derive_report.md"
        return (PROMPTS_DIR / fname).read_text(encoding="utf-8-sig")

    def _run_llm(self, kind: str, plan: Plan, slides, doc: str,
                 on_attempt=None) -> tuple[dict, int, list[Finding]]:
        tool = SLIDES_TOOL if kind == "slides" else REPORT_TOOL
        tool_name = tool["function"]["name"]
        user_text = render_slides_text(plan, slides, doc)
        messages = [
            {"role": "system", "content": self._system_prompt(kind)},
            {"role": "user", "content": user_text},
        ]

        last_kind = ""    # 마지막 검증 실패 종류: "schema" ("" = 판정 없음 — 도구 미호출 소진)
        last_detail = ""  # 해당 실패의 진단 본문 — builder 스키마 오류문
        validated = 0     # 검증 판정이 이루어진 시도 수 (소진 총계와의 차 = nudge 소비분)

        def validate(args: dict) -> tuple[str, object]:
            nonlocal last_kind, last_detail, validated
            validated += 1
            payload = dict(args)
            self._snap_literals(slides, payload)  # 수치 리터럴 표기 보정 (원칙 3)
            try:
                self._validate_schema(kind, payload)
            except ValueError as e:  # 스키마 위반 — 빌더 검증 오류를 그대로 되돌려 재변환
                last_kind, last_detail = "schema", f"  - {e}"
                return ("retry",
                        f"스키마 검증 실패 — 아래 오류를 해소해 {tool_name} 도구를 다시 호출하라:\n{e}")
            # 수치 위반은 여기서 막지 않는다 — 측정해 검수 단계에 이관 (결정 17)
            return ("ok", payload)

        # 재변환 루프 — LangGraph tool 루프 (편차 11, planforge/llm/loops.py)
        # 도구 누락 nudge·재시도 피드백(assistant.tool_calls → tool 응답 쌍 — ollama cloud
        # 무응답 사고 대응)은 loops.py가 동일 프로토콜로 조립한다.
        final = run_tool_loop(self.chat_fn, [tool], tool_name,
                              max_attempts=self.max_attempts,
                              nudge_text=(f"{tool_name} 도구를 호출해 변환 결과를 전달하라. "
                                          "도구 호출 외 출력 금지."),
                              validate=validate, messages=messages,
                              on_attempt=on_attempt)
        if final["result"] is None:
            raise self._final_error(tool_name, final, last_kind, last_detail, validated)
        payload = final["result"]
        # numcheck 1회 측정 — 게이트가 아니다: 수치 판정 권위는 검수 단계(결정 17).
        # 측정값은 DeriveResult·job.result로 보고되고 red 잔여는 검수를 자동 큐잉한다.
        findings = self._numcheck(kind, plan, slides, payload)
        return payload, final["attempts"], findings

    def _final_error(self, tool_name: str, final: dict, last_kind: str,
                     last_detail: str, validated: int) -> DeriveError:
        """소진 오류 — 마지막으로 관측된 실패 종류에 맞는 라벨·진단 본문으로 만든다.

        소진되는 실패는 스키마 위반 지속이 유일하다(결정 17 — 수치는 측정 후 진행).
        검증 판정 없이 소진되면(도구 미호출) 그 사실을 본문에 고지한다.
        (결정 16 — 소진 오류에 실제 라벨·진단. 재시도 피드백 문구는 불변.)
        """
        msg: str
        misses = final["attempts"] - validated  # 도구 없이 텍스트로만 끝난 응답 수
        if last_kind == "schema":
            msg = (f"스키마 검증 실패가 {self.max_attempts}회 재시도 후에도 해소되지 않았습니다 "
                   f"— LLM 결과가 {tool_name} 스키마 요구 구조를 만족하지 못했습니다:\n"
                   + last_detail)
        else:
            # 검증 판정 없이 소진 — LLM이 끝까지 도구를 호출하지 않음 (nudge 소진)
            preview = final.get("resp_content") or ""
            if len(preview) > 500:
                preview = preview[:500] + "…"
            msg = (f"LLM이 {final['attempts']}회 응답 동안 {tool_name} 도구를 호출하지 않았습니다 "
                   "— 변환 결과가 도구 호출로 전달되지 않았습니다.\n"
                   f"마지막 응답(앞 500자): {preview or '(텍스트 응답 없음)'}")
        if validated and misses:
            msg += (f"\n\n(참고: 마지막 {misses}회 응답은 {tool_name} 도구 호출 없이 "
                    "텍스트로만 반응했다 — 재시도가 무응답으로 끝났다)")
        return DeriveSchemaError(msg) if last_kind == "schema" else DeriveError(msg)

    def _snap_literals(self, slides, payload: dict) -> None:
        """LLM이 정규화한 수치 리터럴(15.0→15)을 plan 표기로 되돌린다 (결정론 보정).

        chart/data 값이 plan의 어떤 수치와 **값이 같을 때만** plan의 리터럴
        (int/float 구분 — 파서가 원본 표기 보존)로 교체한다. 값이 다르면 건드리지
        않는다 — 그런 위반은 numcheck가 red로 기록해 검수 단계 판정으로 넘긴다 (원칙 3, 결정 17).
        """
        plan_lits: dict[float, object] = {}
        for s in slides:
            if s.chart is not None:
                for sr in s.chart.series:
                    for v in sr.values:
                        try:
                            plan_lits[float(v)] = v
                        except (TypeError, ValueError):
                            continue
        if not plan_lits:
            return

        def snap(v):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return v
            tok = plan_lits.get(float(v))
            if tok is None or str(v) == str(tok):
                return v
            return tok  # 파서가 만든 int|float 리터럴 — JSON 표기가 plan과 같아진다

        if payload.get("slides") is not None:
            for sl in payload["slides"]:
                chart = sl.get("chart") if isinstance(sl, dict) else None
                if chart:
                    chart["series"] = [
                        {**sr, "values": [snap(v) for v in sr.get("values", [])]}
                        for sr in chart.get("series", []) if isinstance(sr, dict)]
        else:
            for sec in payload.get("sections", []):
                for b in (sec.get("blocks") or []) if isinstance(sec, dict) else []:
                    if isinstance(b, dict) and b.get("kind") == "data":
                        for sr in b.get("series", []):
                            if isinstance(sr, dict):
                                sr["values"] = [snap(v) for v in sr.get("values", [])]

    def _validate_schema(self, kind: str, payload: dict) -> None:
        """builder 스키마 검증 — 위반은 ValueError로 올려 validate 클로저가 재변환을 유도한다."""
        if kind == "slides":
            from .builders import build_ppt
            build_ppt.validate(payload)
        else:
            from .builders import build_doc
            build_doc.validate(payload)

    def _numcheck(self, kind: str, plan: Plan, slides, payload: dict) -> list[Finding]:
        """수치 무결성 측정 — 판정 게이트가 아니라 기록이다 (결정 17: 권위는 검수 단계).

        스키마 통과 payload에만 호출된다. 검수(run_review)가 같은 엔진을 파생물 d.json에
        재적용하므로 이 측정값과 검수 리포트 발견사항이 일치한다."""
        if kind == "slides":
            return check_slides(slides, plan.key_messages, payload)
        return check_report(slides, plan.key_messages, payload)

    # ---- 파생물 생성

    def derive(self, plan_path: str | Path, kind: str, doc: str | None = None, *,
               on_attempt=None) -> DeriveResult:
        """on_attempt(attempt, max_attempts) — LLM 변환 시도 직전 콜백 (진행 상황 기록용).
        planforge는 DB를 모른다 — 예외 방어는 caller 콜백 쪽 책임."""
        if kind not in ("slides", "report"):
            raise DeriveError(f"kind는 slides|report 중 하나여야 합니다: {kind}")
        plan, doc, slides, unconfirmed = self._prepare(plan_path, doc)
        payload, attempt, findings = self._run_llm(kind, plan, slides, doc, on_attempt=on_attempt)

        # 결정론 보정 — meta.title은 대상 문서 표지 슬라이드 제목 (make-ppt/make-doc 규칙)
        cover = next((s for s in slides if s.type == "cover"), None)
        if cover is not None:
            payload.setdefault("meta", {})["title"] = cover.title
        if kind == "report":
            payload.setdefault("meta", {})["doc_type"] = doc
        else:
            payload.setdefault("meta", {}).setdefault("title", plan.title)

        self.workspace.joinpath("work").mkdir(parents=True, exist_ok=True)
        work_path = self.workspace / "work" / ("slides.json" if kind == "slides" else "report.json")
        work_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        res = DeriveResult(work_path=work_path, attempts=attempt, unconfirmed=unconfirmed,
                           findings=findings)
        if kind == "slides":
            res.slides_count = len(payload["slides"])
        else:
            res.sections_count = len(payload["sections"])
        return res

    # ---- 빌더 실행 (결정론 — 채번·조립은 코드)

    def build(self, kind: str, fmts: tuple[str, ...] = ()) -> list[Path]:
        """빌더 실행 → output/<title>_vNN.<ext>. 무손실 채번은 빌더가 담당 (원칙 5)."""
        work = self.workspace / "work" / ("slides.json" if kind == "slides" else "report.json")
        out_dir = self.workspace / "output"
        made: list[Path] = []
        if kind == "slides":
            from .builders import build_ppt
            build_ppt.build(str(work), str(out_dir))
            made += list(out_dir.glob("*.pptx"))
        else:
            from .builders import build_doc
            for fmt in (fmts or ("md", "html", "docx")):
                build_doc.build(str(work), fmt, str(out_dir))
                made += list(out_dir.glob(f"*.{fmt}"))
        return made