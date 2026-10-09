"""위험 Bash/PowerShell 명령어 가드 훅.

PreToolUse 훅으로 Bash/PowerShell 도구의 명령어가 되돌릴 수 없는 파괴 명령이면
차단(exit 2)한다. execute.py 하네스의 자식 claude 세션
(--dangerously-skip-permissions)에서도 훅은 실행되므로, 자식 세션의 안전 레이어
역할을 한다. 판단 불가 시 차단하지 않는 파기 개방(fail-open) 정책은 guard_ssot과
동일하다.
"""
import json
import re
import sys

DANGEROUS_PATTERNS = [
    # 재귀 강제 삭제
    r"rm\s+(-\w+\s+)*-[a-z]*[rf]{2,}",  # rm -rf, rm -fr ...
    r"Remove-Item\s+(.*\s)?-Recurse.*-Force",  # PowerShell 재귀삭제
    r"rmdir\s+/s",
    r"del\s+/s",
    # 되돌릴 수 없는 git/DML 연산
    r"git\s+push\s+.+--force",
    r"git\s+reset\s+--hard",
    r"DROP\s+(TABLE|DATABASE)",
    # 시스템 파괴
    r"format\s+[A-Za-z]:",
]

MESSAGE = """BLOCKED: 되돌릴 수 없는 위험 명령어가 감지되었습니다.
- 감지된 명령: '{cmd}'
- 이 명령은 파괴적이라 자동 실행이 차단됩니다. 정말 필요하면 사용자에게 확인 후 진행하세요."""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # 판단 불가 시 차단하지 않음

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        return 0

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            sys.stderr.write(MESSAGE.format(cmd=command))
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())