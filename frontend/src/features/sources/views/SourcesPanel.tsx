import { useState } from "react";
import { FileCode, FileText, Upload } from "lucide-react";
import { Banner, Button, Empty } from "../../../shared/components/ui";
import { MAX_SOURCE_MB, MAX_ZIP_MB } from "../../../shared/lib/uploadLimits";
import { useOverviewMeta } from "../viewmodels/useOverview";
import { useSources } from "../viewmodels/useSources";
import OverviewEditor from "./OverviewEditor";
import { SourceDeleteModal } from "./SourceDeleteModal";
import { SourceTable } from "./SourceTable";

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
    uploadReport,
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

  return (
    <>
      <section>
        {error && <Banner kind="error">{error}</Banner>}

        {uploadReport && (
          <Banner kind="info">
            {uploadReport.savedCount > 0 &&
              `${uploadReport.savedCount}건의 소스를 저장했습니다.`}
            {uploadReport.savedCount > 0 && uploadReport.skipped.length > 0 && " "}
            {uploadReport.skipped.length > 0 && (
              <ul className="upload-skip-list">
                {uploadReport.skipped.map((s) => (
                  <li key={s.name}>
                    {`${s.name} — ${s.reason}`}
                  </li>
                ))}
              </ul>
            )}
          </Banner>
        )}

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
            <SourceTable files={files} dir="project" pid={pid} onDelete={openDelete} />
          )}
          <div className="panel-foot">
            <span className="hint sources-foot-desc">
              인터뷰 에이전트와 기획서 생성의 기초 팩트로 활용될 수집 문서를 등록·관리합니다. (.md .txt .json .csv, 최대 {MAX_SOURCE_MB}MB · UTF-8 · PDF 미지원)
              zip 업로드는 압축을 해제해 등록하며 (zip 파일 자체는 최대 {MAX_ZIP_MB}MB), zip 내부 파일도 동일 규칙(확장자·{MAX_SOURCE_MB}MB·UTF-8)이 적용됩니다. 기존 소스는 덮어쓰지 않습니다.
            </span>
            <label className="upload-label">
              <Upload aria-hidden="true" />
              신규 문서 업로드
              <input
                ref={fileInput}
                type="file"
                accept=".md,.txt,.json,.csv,.zip"
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
            <SourceTable files={globalFiles} dir="global" pid={pid} onDelete={openDelete} />
          )}
        </div>
      </section>

      {/* 삭제 확인 모달 — ProjectsPage 삭제 모달과 동일 스타일 (파일명 입력 절차는 생략) */}
      {delTarget && (
        <SourceDeleteModal
          name={delTarget}
          delBusy={delBusy}
          delError={delError}
          onConfirm={() => void confirmDelete()}
          onClose={closeDelete}
        />
      )}
    </>
  );
}
