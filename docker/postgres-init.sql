-- 개발(reportagent) + 병행 개발(reportagent_dev) + 테스트(reportagent_test) DB 생성
-- POSTGRES_DB=reportagent가 이미 생성되므로 나머지를 추가한다.
-- 컨테이너 재생성 시에만 실행된다 — 기존 컨테이너 재시작에는 적용되지 않는다.
CREATE DATABASE reportagent_dev;
CREATE DATABASE reportagent_test;
GRANT ALL PRIVILEGES ON DATABASE reportagent_dev TO reportagent;
GRANT ALL PRIVILEGES ON DATABASE reportagent_test TO reportagent;
