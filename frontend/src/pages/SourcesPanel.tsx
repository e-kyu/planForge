import { useEffect, useRef, useState } from "react";
import { FileCode, Trash2, Upload } from "lucide-react";
import {
  apiDelete,
  apiGet,
  apiUpload,
  ApiError,
  type SourceFile,
} from "../api/client";
import { Banner, Empty, PageHeader, fmtBytes } from "../components/ui";

const MAX_MB = 2;

const fmtEpoch = (sec: number) => {
  const d = new Date(sec * 1000); // st_mtime — float epoch 초
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

/** 포맷 배지 — API에 type 필드가 없어 확장자에서 도출 (설계 D6). */
const extOf = (name: string) => name.split(".").pop()?.toUpperCase() ?? "";

/** 소스 관리 (FR-2.1) — 인터뷰 시작 전 확인하는 소스 문서.
 *  프로젝트 sources/는 업로드·삭제 가능, 글로벌 sources/는 읽기 전용. */
export default function SourcesPanel({ pid }: { pid: number }) {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [globalFiles, setGlobalFiles] = useState<SourceFile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      const [own, glob] = await Promise.all([
        apiGet<SourceFile[]>(`/api/projects/${pid}/sources`),
        apiGet<SourceFile[]>("/api/sources"),
      ]);
      setFiles(own);
      setGlobalFiles(glob);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }
  useEffect(() => {
    void load();
  }, [pid]);

  async function upload(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    setError(null);
    try {
      for (const f of Array.from(fileList)) {
        if (f.size > MAX_MB * 1024 * 1024) {
          throw new Error(`${f.name}: ${MAX_MB}MB 초과`);
        }
        await apiUpload<SourceFile>(`/api/projects/${pid}/sources`, f);
      }
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function remove(name: string) {
    setError(null);
    try {
      await apiDelete(`/api/projects/${pid}/sources/${encodeURIComponent(name)}`);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

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
                {dir === "project" ? (
                  <button
                    type="button"
                    className="row-del"
                    onClick={() => void remove(s.name)}
                    aria-label={`${s.name} 삭제`}
                    title="삭제"
                  >
                    <Trash2 />
                  </button>
                ) : (
                  <span className="badge badge-global">읽기 전용</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <section>
      <PageHeader
        icon={FileCode}
        title="소스 데이터 문서 (Sources)"
        desc={`인터뷰 에이전트와 기획서 생성의 기초 팩트로 활용될 수집 문서를 등록·관리합니다. (.md .txt .json .csv, 최대 ${MAX_MB}MB · UTF-8 · PDF 미지원)`}
      >
        <label className="upload-label">
          <Upload aria-hidden="true" />
          신규 문서 업로드
          <input
            ref={fileInput}
            type="file"
            accept=".md,.txt,.json,.csv"
            multiple
            onChange={(e) => void upload(e.target.files)}
            data-testid="source-file-input"
          />
        </label>
      </PageHeader>
      {error && <Banner kind="error">{error}</Banner>}

      <div className="card">
        <div className="panel-head">
          <h4>프로젝트 소스</h4>
          <span className="hint">{files === null ? "" : `${files.length}건`}</span>
        </div>
        {files === null ? null : files.length === 0 ? (
          <Empty>업로드된 소스가 없습니다.</Empty>
        ) : (
          table(files, "project")
        )}
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
  );
}