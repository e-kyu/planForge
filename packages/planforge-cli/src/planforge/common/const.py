# -*- coding: utf-8 -*-
"""엔진 공용 상수 — 값·판정 의미는 불변이다.

(미확정)의 두 매칭 의미는 통합하지 않는다:
- `UNCONFIRMED_PREFIX`(`(미확정`) — numcheck·derive·review. "(미확정)"·"(미확정 - 사유)"
  변형을 모두 잡는다.
- `UNCONFIRMED_EXACT`(`(미확정)`) — compact. 정확 일치만.
하나로 합치면 판정 동작이 바뀐다.
"""

UNCONFIRMED_PREFIX = "(미확정"
UNCONFIRMED_EXACT = "(미확정)"
DEFAULT_DOC_NAME = "제안서"
DERIVATIVE_KINDS = ("slides", "report")
REPORT_FORMATS = ("md", "html", "docx")
KEY_MESSAGE_COUNT = 3
MAX_ARCH_GROUPS = 6
MAX_ARCH_ITEMS = 6
