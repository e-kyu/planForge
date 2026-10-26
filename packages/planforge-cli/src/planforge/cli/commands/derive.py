# -*- coding: utf-8 -*-
"""`planforge derive` — plan.md → 파생물 생성 (LLM 변환 + 빌드)."""
from __future__ import annotations

from ...common.configpath import resolve_config_path
from ...plan.loader import load_plan_for_doc


def cmd_derive(args) -> int:
    from ...derive import Deriver
    from ...llm import get_provider, load_config

    config_path = resolve_config_path(args.config)
    if not config_path.is_file():
        print(f"오류: LLM 설정 파일이 없습니다: {config_path}")
        print("backend/planforge/config.example.json을 config.json으로 복사해 모델을 지정하거나,")
        print("환경변수 PLANFORGE_CONFIG로 경로를 지정하세요.")
        return 2
    profiles = load_config(config_path)
    provider = get_provider(profiles["derive"])

    # (미확정) 수치 전제 확인 (make-ppt/make-doc 전제 절차 이식) — 로더가 파싱·필터·골격·
    # (미확정) 탐지를 한 번에 하며, 그 결과를 Deriver에 그대로 넘겨 재파싱하지 않는다.
    prepared = load_plan_for_doc(args.plan, args.doc)
    if prepared.unconfirmed and not args.allow_unconfirmed:
        print(f"(미확정) 표기가 남은 슬라이드: {prepared.unconfirmed} — 확정 수치로 채울지 확인이 필요합니다.")
        print("그대로 진행하려면 --allow-unconfirmed 옵션을 사용하세요.")
        return 2

    d = Deriver(provider.chat, args.workspace)
    res = d.derive(args.plan, args.kind, args.doc, prepared=prepared)
    print(f"OK: {res.work_path} (시도 {res.attempts}회, "
          + (f"슬라이드 {res.slides_count}개" if args.kind == "slides" else f"섹션 {res.sections_count}개") + ")")
    if res.findings:
        # 결정 17 — 측정만 하고 진행한다(생성 실패 아님). 판정 권위는 검수 단계.
        reds = sum(1 for f in res.findings if f.severity == "red")
        print(f"주의: 수치 무결성 대조에서 미달 {len(res.findings)}건 (🔴 {reds}건)")
        for f in res.findings:
            print(f"  - {f}")
        print("수치 판정은 검수 단계 소관입니다 (결정 17) — 위반 여부 게이트는 "
              "`python -m planforge numcheck`(exit 1 계약)로 별행하세요.")
    if res.unconfirmed:
        print(f"주의: (미확정) 표기 슬라이드 {res.unconfirmed} — 산출물에 그대로 유지됩니다")
    if args.no_build:
        return 0
    outs = d.build(args.kind, tuple(args.fmts) if args.fmts else ())
    for o in outs:
        print(f"산출물: {o}")
    return 0
