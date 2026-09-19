# -*- coding: utf-8 -*-
"""파생물 생성 오케스트레이터 (make-ppt·make-doc 이식).

LLM/코드 역할 분리:
- 결정론(코드): 문서 필터·골격 검증·스키마 검증(builder.validate)·수치 무결성 대조(numcheck)·
  파일 기록·빌더 실행·채번.
- LLM: plan 표기 → slides.json/report.json 콘텐츠 변환 (도구 호출 1회). 수치 무결성 위반 시
  발견사항을 되돌려 재변환 요청 (최대 N회) — 코드가 판정하고 LLM이 고친다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

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
    """파생물 생성 실패 (LLM 미응답·스키마 위반 지속·수치 무결성 미달 지속)."""


@dataclass
class DeriveResult:
    work_path: Path
    slides_count: int = 0
    sections_count: int = 0
    unconfirmed: list[int] = field(default_factory=list)  # (미확정) 표기가 남은 슬라이드 번호
    findings: list[Finding] = field(default_factory=list)   # 최종 승인 시 남은 yellow 등
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

    def _run_llm(self, kind: str, plan: Plan, slides, doc: str) -> tuple[dict, int]:
        tool = SLIDES_TOOL if kind == "slides" else REPORT_TOOL
        tool_name = tool["function"]["name"]
        user_text = render_slides_text(plan, slides, doc)
        messages = [
            {"role": "system", "content": self._system_prompt(kind)},
            {"role": "user", "content": user_text},
        ]

        def _feedback(resp_content: str, args_json: str, text: str) -> None:
            """도구 호출 결과를 프로토콜대로 되돌린다 (assistant.tool_calls → tool 응답).

            tool 응답 없이 user 피드백만 붙이면 OpenAI 호환 릴레이가 요청을 처리하지
            못하고 정지한다 (사고: ollama cloud 재시도 요청 무응답).
            """
            messages.append({"role": "assistant", "content": resp_content or None,
                             "tool_calls": [{"id": f"call_{tool_name}", "type": "function",
                                             "function": {"name": tool_name,
                                                          "arguments": args_json}}]})
            messages.append({"role": "tool", "tool_call_id": f"call_{tool_name}",
                             "content": text})

        last_findings: list[Finding] = []
        for attempt in range(1, self.max_attempts + 1):
            resp = self.chat_fn(messages, tools=[tool])
            calls = [tc for tc in resp.get("tool_calls", []) if tc["name"] == tool_name]
            if not calls:
                messages.append({"role": "assistant", "content": resp.get("content") or ""})
                messages.append({"role": "user", "content":
                                 f"{tool_name} 도구를 호출해 변환 결과를 전달하라. 도구 호출 외 출력 금지."})
                continue
            args = calls[0]["arguments"]
            if isinstance(args, str):
                args = json.loads(args)
            args_json = json.dumps(args, ensure_ascii=False)
            payload = dict(args)
            self._snap_literals(slides, payload)  # 수치 리터럴 표기 보정 (원칙 3)
            try:
                findings = self._check(kind, plan, slides, payload)
                reds = [f for f in findings if f.severity == "red"]
            except ValueError as e:  # 스키마 위반 — 빌더 검증 오류를 그대로 되돌려 재변환
                _feedback(resp.get("content") or "", args_json,
                          f"스키마 검증 실패 — 아래 오류를 해소해 {tool_name} 도구를 다시 호출하라:\n{e}")
                continue
            if not reds:
                return payload, attempt, last_findings
            last_findings = findings
            _feedback(resp.get("content") or "", args_json,
                      "수치 무결성 검증 실패(🔴). 아래 발견사항을 모두 해소해 "
                      f"{tool_name} 도구를 다시 호출하라. 수치 토큰은 plan 표기를 문자열 "
                      "그대로 복사한다 — 소수점 자리·단위·기호를 정규화하지 않는다 "
                      "(15.0→15 금지, '15.0억 원'→'15.0억' 금지):\n"
                      + "\n".join(str(f) for f in reds))
        raise DeriveError(
            f"수치 무결성 위반이 {self.max_attempts}회 재시도 후에도 해소되지 않았습니다 "
            "(수치·표·차트는 plan과 한 글자도 같아야 합니다):\n"
            + "\n".join(str(f) for f in last_findings))

    def _snap_literals(self, slides, payload: dict) -> None:
        """LLM이 정규화한 수치 리터럴(15.0→15)을 plan 표기로 되돌린다 (결정론 보정).

        chart/data 값이 plan의 어떤 수치와 **값이 같을 때만** plan의 리터럴
        (int/float 구분 — 파서가 원본 표기 보존)로 교체한다. 값이 다르면 건드리지
        않는다 — 그런 위반은 numcheck가 red로 잡아 재변환을 유도한다 (원칙 3).
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

    def _check(self, kind: str, plan: Plan, slides, payload: dict) -> list[Finding]:
        if kind == "slides":
            from .builders import build_ppt
            build_ppt.validate(payload)  # 스키마 위반은 검증 오류로 재시도 유도 아님 — 예외 전파
            return check_slides(slides, plan.key_messages, payload)
        from .builders import build_doc
        build_doc.validate(payload)
        return check_report(slides, plan.key_messages, payload)

    # ---- 파생물 생성

    def derive(self, plan_path: str | Path, kind: str, doc: str | None = None) -> DeriveResult:
        if kind not in ("slides", "report"):
            raise DeriveError(f"kind는 slides|report 중 하나여야 합니다: {kind}")
        plan, doc, slides, unconfirmed = self._prepare(plan_path, doc)
        payload, attempt, _ = self._run_llm(kind, plan, slides, doc)

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
        res = DeriveResult(work_path=work_path, attempts=attempt, unconfirmed=unconfirmed)
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