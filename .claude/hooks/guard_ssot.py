"""SSOT 가드 훅 — 파생물 직접 수정 차단 (설계 원칙 계약 1번).

PreToolUse 훅으로 Edit/Write 계열 도구의 대상 경로가 파생물(slides.json,
report.json, output/*)이면 차단(exit 2)한다. 파생물은 항상 plan에서 재생성한다.
"""
import json
import re
import sys

PROTECTED_PATTERNS = [
    # 워크스페이스 파생물: workspaces/<slug>/work/slides.json, report.json
    r"workspaces[/\\][^/\\]+[/\\]work[/\\](slides|report)\.json$",
    # 산출물 디렉토리 전체: workspaces/<slug>/output/..., 기타 output/ 경로
    r"[/\\]output[/\\]",
]

MESSAGE = """SSOT 위반 감지: '{path}' 는 파생물/산출물이므로 직접 수정할 수 없습니다.
- 파생물(slides.json, report.json)은 plan.md(Plan 레코드)에서 재생성해야 합니다.
- 산출물은 빌더(run_builder)가 채번해서 생성해야 하며, 어떤 경우에도 덮어쓰지 않습니다.
수정이 필요하면 plan을 수정한 뒤 파생 단계를 다시 실행하는 경로로 구현하세요.
(테스트 fixture를 만드는 경우 workspaces/ 대신 tests/fixtures/ 를 사용하세요.)"""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # 판단 불가 시 차단하지 않음

    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        return 0

    normalized = file_path.replace("\\", "/")
    for pattern in PROTECTED_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            sys.stderr.write(MESSAGE.format(path=file_path))
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())