import { useEffect, useState } from "react";
import { Download, FileCode, FileText, Trash2, Upload, X } from "lucide-react";
import type { SourceFile } from "../../../api/client";
import { Banner, Button, Empty, fmtBytes } from "../../../shared/components/ui";
import { useOverviewMeta } from "../viewmodels/useOverview";
import { MAX_MB, useSources } from "../viewmodels/useSources";
import OverviewEditor from "./OverviewEditor";

const fmtEpoch = (sec: number) => {
  const d = new Date(sec * 1000); // st_mtime — float epoch 초
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

/** 포맷 배지 — API에 type 필드가 없어 확장자에서 도출 (설계 D6). */
const extOf = (name: string) => name.split(".").pop()?.toUpperCase() ?? "";

/** 소스 관리 (FR-2.1) — 목록 ↔ 개요 문서 편집기 스위칭 (표현 전용 View). */
export default function SourcesPanel({ pid }: { pid: number }) {
  const [overviewEdit, setOverviewEdit] = useState(false);
  return overviewEdit ? (
    <OverviewEditor pid={pid} onBack={() => setOverviewEdit(false)} />
  ) : (
    <SourcesList pid={pid} onStartOverview={() => setOverviewEdit(true)} />
  );
}

function SourcesList({ pid, onStartOverview }: { pid: number; onStartOverview: () => void }) {
  const {
    files,
    globalFiles,
    error,
    upload,
    delTarget,
    delBusy,
    delError,
    openDelete,
    closeDelete,
    confirmDelete,
    fileInput,
  } = useSources(pid);
  const { meta: overview } = useOverviewMeta(pid);

  // Esc로 삭제 확인 모달 닫기 — 작업 중에는 닫지 않음
  useEffect(() => {
    if (!delTarget) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (!delBusy) closeDelete();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [delTarget, delBusy, closeDelete]);

  const downloadHref = (dir: "project" | "global", name: string) =>
    dir === "project"
      ? `/api/projects/${pid}/sources/${encodeURIComponent(name)}/download`
      : `/api/sources/${encodeURIComponent(name)}/download`;

  const table = (fs: SourceFile[], dir: "project" | "global") => (
    <div className="table-wrap">
      <table className="source-table">
        <thead>
          <tr>
            <th>문서명</th>
            <th>포맷</th>
            <th>파일 크기</th>
            <th>등록일시</th>
            <th className="th-actions">작업</th>
          </tr>
        </thead>
        <tbody>
          {fs.map((s) => (
            <tr key={`${dir}:${s.name}`}>
              <td>
                <span className="source-name-cell">
                  <FileCode aria-hidden="true" />
                  <span className="source-name">{s.name}</span>
                </span>
              </td>
              <td>
                <span className="ext-badge">{extOf(s.name)}</span>
              </td>
              <td className="source-meta">{fmtBytes(s.size)}</td>
              <td className="source-meta">{fmtEpoch(s.mtime)}</td>
              <td>
                <span className="row-actions">
                  <a
                    className="row-dl"
                    href={downloadHref(dir, s.name)}
                    download
                    aria-label={`${s.name} 다운로드`}
                    title="다운로드"
                  >
                    <Download aria-hidden="true" />
                  </a>
                  {dir === "project" && (
                    <button
                      type="button"
                      className="row-del"
                      onClick={() => openDelete(s.name)}
                      aria-label={`${s.name} 삭제`}
                      title="삭제"
                    >
                      <Trash2 />
                    </button>
                  )}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <>
      <section>
        {error && <Banner kind="error">{error}</Banner>}

        <div className="card">
          <div className="panel-head">
            <div className="sources-head-text">
              <h4>
                <FileCode aria-hidden="true" />
                소스 데이터 문서 (Sources)
              </h4>
              {files === null ? null : <span className="hint">{`${files.length}건`}</span>}
            </div>
          </div>
          {files === null ? null : files.length === 0 ? (
            <Empty>업로드된 소스가 없습니다.</Empty>
          ) : (
            table(files, "project")
          )}
          <div className="panel-foot">
            <span className="hint sources-foot-desc">
              인터뷰 에이전트와 기획서 생성의 기초 팩트로 활용될 수집 문서를 등록·관리합니다. (.md .txt .json .csv, 최대 {MAX_MB}MB · UTF-8 · PDF 미지원)
            </span>
            <label className="upload-label">
              <Upload aria-hidden="true" />
              신규 문서 업로드
              <input
                ref={fileInput}
                type="file"
                accept=".md,.txt,.json,.csv"
                multiple
                onChange={(e) => upload(e.target.files)}
                data-testid="source-file-input"
              />
            </label>
            <Button onClick={onStartOverview}>
              <FileText aria-hidden="true" />
              {overview?.exists ? "개요 편집" : "개요 작성"}
            </Button>
          </div>
        </div>

        <div className="card">
          <div className="panel-head">
            <h4>글로벌 소스</h4>
            <span className="hint">서버 공용 (sources/)</span>
          </div>
          {globalFiles === null ? null : globalFiles.length === 0 ? (
            <Empty>글로벌 소스가 없습니다.</Empty>
          ) : (
            table(globalFiles, "global")
          )}
        </div>
      </section>

      {/* 삭제 확인 모달 — ProjectsPage 삭제 모달과 동일 스타일 (파일명 입력 절차는 생략) */}
      {delTarget && (
        <div className="modal-overlay" onClick={delBusy ? undefined : closeDelete}>
          <div
            className="modal modal-del"
            role="dialog"
            aria-modal="true"
            aria-labelledby="source-delete-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h3 id="source-delete-title">소스 삭제</h3>
              <button
                className="modal-close"
                onClick={closeDelete}
                disabled={delBusy}
                aria-label="닫기"
              >
                <X />
              </button>
            </div>
            <p className="hint del-warn">
              소스는 휴지통 없이 영구 삭제되며 되돌릴 수 없습니다.
            </p>
            <p className="del-target">
              삭제할 소스: <strong>{delTarget}</strong>
            </p>
            {delError && <Banner kind="error">{delError}</Banner>}
            <div className="modal-actions">
              <Button variant="ghost" onClick={closeDelete} disabled={delBusy}>
                취소
              </Button>
              <Button variant="danger" onClick={() => void confirmDelete()} disabled={delBusy}>
                삭제
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}