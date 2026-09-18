-- 개발(reportagent) + 테스트(reportagent_test) DB 생성
-- POSTGRES_DB=reportagent가 이미 생성되므로 테스트 DB만 추가한다.
CREATE DATABASE reportagent_test;
GRANT ALL PRIVILEGES ON DATABASE reportagent_test TO reportagent;