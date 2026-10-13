import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Build } from "../../../api/client";
import type { DocSlug } from "../../projects/models/docloops";
import { enqueueDerivative, fetchBuilds, fetchOutputText, fetchPlans } from "../models/outputsApi";
import { latestDoneDeriveWithReds, latestFailed } from "../../../shared/lib/jobs";
import { seedJob, useActiveJobs } from "../../../shared/lib/useActiveJobs";
import { useTickingNow } from "../../../shared/lib/useTickingNow";
import { errMsg } from "../../../shared/lib/errMsg";

/* 산출물 갤러리 (FR-3.4/3.5, FR-5) — 갤러리·작업 큐·미리보기 데이터.
 * 잡 폴링 소유자는 공용 useActiveJobs (헤더 ActivityPill과 같은 캐시) — 여기선 캐시를
 * 소비만 한다. 큐가 비워지면(완료) 갤러리·plan 쿼리를 무효화해 갱신한다 — 원본 폴링의
 * 완료 경로 (마지막 load()에서 갤러리까지 재조회)에 해당한다. */

export function useOutputs(pid: number, doc: DocSlug | null = null) {
  const qc = useQueryClient();
  // 문서 라우트에서는 해당 문서의 산출물·세대만 조회(?doc_slug=) — 쿼리 키에 doc을 넣어 캐시 분리.
  // ["builds", pid]·["plans", pid] 프리픽스 무효화는 문서 스코프 캐시도 함께 무효화한다.
  const buildsQ = useQuery({
    queryKey: ["builds", pid, doc],
    queryFn: () => fetchBuilds(pid, doc),
  });
  const plansQ = useQuery({
    queryKey: ["plans", pid, doc],
    queryFn: () => fetchPlans(pid, doc),
  });
  const jobsS = useActiveJobs(pid);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [sel, setSel] = useState<Build | null>(null);
  const [selPreview, setSelPreview] = useState<string | null>(null);

  const jobs = jobsS.jobs;
  const active = jobsS.active;
  // 경과 갱신 틱 — 조건은 some(running) (activeJob은 latestActive이 running 우선이라
  // 직렬 워커 하에서 동치지만, 틱은 상태 모음 전체 기준이 안전하다).
  const now = useTickingNow(jobs.some((j) => j.status === "running"));
  // 실패 배너는 이력이 아니라 마지막 상태 기준 — 타입별 최신 job이 실패일 때만 노출
  const failedLatest = useMemo(() => latestFailed(jobs), [jobs]);
  // 수치 위반 잔여 배너 — 최신 클린 생성이 이를 대체한다 (결정 17: 측정 기록은 job.result에 영속)
  const residualJob = useMemo(() => latestDoneDeriveWithReds(jobs), [jobs]);
  // 상태창 배너가 가리킬 활성 잡 — queued/running 중 최신 1건 (진행 문구·경과 표시용)
  const activeJob = jobsS.activeJob;
  const busy = pending || active;

  // 활성 → 비활성 전환(잡 완료) 시 갤러리·plan 갱신 — 원본 폴링 완료 경로 동작 보존
  const prevActiveRef = useRef(false);
  useEffect(() => {
    if (prevActiveRef.current && !active) {
      void qc.invalidateQueries({ queryKey: ["builds", pid] });
      void qc.invalidateQueries({ queryKey: ["plans", pid] });
    }
    prevActiveRef.current = active;
  }, [active, qc, pid]);

  async function refresh() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["builds", pid] }),
      qc.invalidateQueries({ queryKey: ["plans", pid] }),
      qc.invalidateQueries({ queryKey: ["jobs", pid] }),
    ]);
  }

  const enqueueM = useMutation({
    mutationFn: (body: {
      kind: "slides" | "report";
      doc_slug?: DocSlug;
      doc?: string;
      fmts?: string[];
    }) => enqueueDerivative(pid, body),
    onSuccess: async (job) => {
      setNotice(`작업 큐 진입 (#${job.id}) — 워커가 직렬 처리합니다.`);
      seedJob(qc, pid, job);
      await refresh();
    },
    onError: (e) => {
      setError(errMsg(e));
      setPending(false);
    },
    onSettled: () => setPending(false),
  });

  /** kind 외 두 문서 개념 구분 — docLabel: plan 본문 `- 산출 문서:` 라인의 한글 유형
   * 라벨(제안서·UI·UX설계서…, View의 docLabelSel → body.doc), doc: 훅 파라미터의
   * 루트 슬러그(DocSlug — 문서 루프 식별자 → body.doc_slug). */
  function enqueue(kind: "slides" | "report", docLabel: string | undefined, fmts?: string[]) {
    setError(null);
    setNotice(null);
    setPending(true);
    // doc이 null인 레거시(플랫) 라우트는 doc_slug 키를 아예 전달하지 않는다 —
    // 백엔드 가드의 레거시 허용 계약과 짝 (doc-loop 프로젝트는 필수, 누락 시 409).
    enqueueM.mutate({ kind, doc: docLabel, fmts, doc_slug: doc ?? undefined });
  }

  /** 미리보기 선택 — md는 본문을 당겨오고, 나머지 확장자는 프레임만 연다. */
  async function preview(b: Build) {
    setSel(b);
    setSelPreview(null);
    if (b.ext === "md") {
      try {
        setSelPreview(await fetchOutputText(pid, b.id));
      } catch {
        setSelPreview("(미리보기를 읽지 못했습니다)");
      }
    }
  }

  function closePreview() {
    setSel(null);
  }

  return {
    builds: buildsQ.data ?? null,
    plans: plansQ.data ?? [],
    jobs,
    failedLatest,
    residualJob,
    activeJob,
    jobsError: jobsS.jobsError,
    now,
    error,
    notice,
    busy,
    enqueue,
    preview,
    sel,
    selPreview,
    closePreview,
  };
}