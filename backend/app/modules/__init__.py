# -*- coding: utf-8 -*-
"""모듈러 모놀리식 모듈 집합 (가이드 §1.2).

각 모듈은 domain / application / infrastructure / presentation 계층과
타 모듈의 유일한 진입점인 facade.py를 가진다. 모듈 __init__이 자신의
models를 임포트하므로, 이 패키지 import가 shared.db.Base.metadata를 채운다
— alembic env.py와 init_db가 이 집계에 의존한다.

경계 규칙: 타 모듈의 테이블·내부 파일을 직접 import하지 않고 facade/shared를 경유한다.
"""
from . import (  # noqa: F401 — metadata 등록
    derivatives,
    facts,
    interview,
    jobs,
    plans,
    projects,
    review,
    sources,
)