import { Banner, Button } from "../../../shared/components/ui";
import { useCompact } from "../viewmodels/useCompact";

/** 팩트 압축 카드 (FR-6.1) — LLM 통합 제안 → 승인 → 아카이브 적용 (표현 전용 View). */
export function CompactCard({ pid }: { pid: number }) {
  const { facts, preview, result, busy, error, propose, apply, close } = useCompact(pid);

  const byId = new Map((facts ?? []).map((f) => [f.id, f]));
  return (
    <div className="card chat-card">
      <div className="chat-card-title">확립 팩트 ({facts?.length ?? "…"}건)</div>
      {error && <Banner kind="error">{error}</Banner>}
      {result && (
        <Banner kind="ok">
          압축 완료 — {result.archived.length}건 아카이브, 활성 {result.active_remaining}건.
          {result.warnings.length > 0 ? ` (${result.warnings.join(" / ")})` : ""}
        </Banner>
      )}
      {preview ? (
        <>
          {preview.warning && <Banner kind="error">{preview.warning}</Banner>}
          {preview.summary && <p className="hint">{preview.summary}</p>}
          {preview.groups.length === 0 ? (
            <p className="hint">통합 대상 중복이 없습니다 — 팩트는 변경되지 않았습니다.</p>
          ) : (
            <ul className="compact-list">
              {preview.groups.map((g, i) => (
                <li key={i}>
                  <span className="hint">{g.reason || g.topic}</span>
                  <ul className="compact-list">
                    <li>✅ 유지: #{g.keep_id} {byId.get(g.keep_id)?.content ?? `#${g.keep_id}`}</li>
                    {g.archive_ids.map((aid) => (
                      <li key={aid}>📦 아카이브: #{aid} {byId.get(aid)?.content ?? `#${aid}`}</li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
          <div className="center-actions">
            {preview.groups.length > 0 && (
              <Button onClick={() => void apply()} disabled={busy || !preview.ok}>
                승인 · 아카이브
              </Button>
            )}
            <Button variant="ghost" onClick={close} disabled={busy}>
              닫기
            </Button>
          </div>
        </>
      ) : (
        <div className="center-actions">
          <Button onClick={() => void propose()} disabled={busy || (facts?.length ?? 0) < 2}>
            팩트 압축 (통합 + 아카이브)
          </Button>
          <span className="hint">
            중복된 이전 팩트를 아카이브로 밀어내고 최종 확정값만 활성에 남깁니다 (FR-6.1).
          </span>
        </div>
      )}
    </div>
  );
}