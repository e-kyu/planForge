import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchOverview, saveOverview } from "../models/overviewApi";
import { errMsg } from "../../../shared/lib/errMsg";
import { fmtBytes } from "../../../shared/components/ui";

/* 개요 문서 (sources/overview.md) — 파일이 곧 SSOT인 fs 네이티브 소스 문서.
   용도: 인터뷰 기본자료 전용 (plan 결과물 생성 체인 미사용). */

export const MAX_MB = 2; // 서버 MAX_SOURCE_BYTES(2MB)와 동일 — 소스 viewmodel과 같은 클라 사전검사

/** 새 개요 문서 시작 뼈대 — LLM 자동생성이 아닌 정적 템플릿으로만 시작한다. */
export const OVERVIEW_TEMPLATE = `# 프로젝트 개요

## 프로젝트 목적

(이 프로젝트가 달성하려는 목표를 적어 주세요.)

## 배경 및 현황

-

## 주요 제약·요구사항

-

## 참고 자료

-
`;

/** 목록 화면용 — 존재 여부만 (개요 작성/편집 라벨 전환). 에디터와 같은 queryKey 캐시를 공유한다. */
export function useOverviewMeta(pid: number) {
  const overviewQ = useQuery({ queryKey: ["overview", pid], queryFn: () => fetchOverview(pid) });
  return {
    meta: overviewQ.data ?? null, // Overview | null (로딩 중 null)
    error: overviewQ.isError ? errMsg(overviewQ.error) : null,
  };
}

/** 에디터 화면용 — 메타 로드 + 저장 뮤테이션 + 편집 문서 상태. */
export function useOverviewEditor(pid: number) {
  const qc = useQueryClient();
  const { meta, error: loadError } = useOverviewMeta(pid);
  const [draft, setDraft] = useState<string | null>(null); // null = 아직 문서를 받지 못함
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // 문서 수신 시 1회만 초기화 — 이후 캐시 갱신(포커스 refetch 등)이 편집 중 draft를 덮지 않는다
  useEffect(() => {
    if (meta && draft === null) setDraft(meta.exists ? meta.content : OVERVIEW_TEMPLATE);
  }, [meta, draft]);

  const saveM = useMutation({
    mutationFn: async (content: string) => {
      if (new Blob([content]).size > MAX_MB * 1024 * 1024)
        throw new Error(`개요 문서의 크기가 ${MAX_MB}MB를 초과합니다`);
      await saveOverview(pid, content);
    },
    onSuccess: async (_, content) => {
      setError(null);
      setNotice(
        `overview.md 저장 — 소스 목록에 등장하며 인터뷰 기본자료로 주입됩니다 (${fmtBytes(new Blob([content]).size)})`,
      );
      // 캐시 무효화 → baseline 갱신(dirty 해제) + 목록의 exists 플래그 전환
      await qc.invalidateQueries({ queryKey: ["overview", pid] });
    },
    onError: (e) => {
      setNotice(null);
      setError(errMsg(e));
    },
  });

  const saved = meta?.exists ? meta.content : "";
  return {
    meta,
    loadError,
    draft,
    setDraft,
    error,
    notice,
    busy: saveM.isPending,
    dirty: draft !== null && draft !== saved,
    save: () => {
      setNotice(null);
      setError(null);
      if (draft !== null) saveM.mutate(draft);
    },
  };
}