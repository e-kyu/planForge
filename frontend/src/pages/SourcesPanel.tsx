import { useEffect, useRef, useState } from "react";
import {
  apiDelete,
  apiGet,
  apiUpload,
  ApiError,
  type SourceFile,
} from "../api/client";
import { Banner, Button, Empty, fmtBytes } from "../components/ui";

const MAX_MB = 2;

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

  const rows = (fs: SourceFile[], dir: "project" | "global") =>
    fs.map((s) => (
      <li key={`${dir}:${s.name}`} className="source-row">
        <span className="source-name">{s.name}</span>
        <span className="source-meta">{fmtBytes(s.size)}</span>
        {dir === "project" ? (
          <Button variant="ghost" onClick={() => void remove(s.name)}>
            삭제
          </Button>
        ) : (
          <span className="badge badge-global">읽기 전용</span>
        )}
      </li>
    ));

  return (
    <section>
      <div className="panel-head">
        <h3>소스 문서</h3>
        <span className="hint">인터뷰 시작 전에 참조할 소스를 올려두세요 (.md .txt .json .csv, 최대 {MAX_MB}MB)</span>
      </div>
      {error && <Banner kind="error">{error}</Banner>}

      <div className="card">
        <div className="panel-head">
          <h4>프로젝트 소스</h4>
          <input
            ref={fileInput}
            type="file"
            accept=".md,.txt,.json,.csv"
            multiple
            onChange={(e) => void upload(e.target.files)}
            data-testid="source-file-input"
          />
        </div>
        {files === null ? null : files.length === 0 ? (
          <Empty>업로드된 소스가 없습니다.</Empty>
        ) : (
          <ul className="source-list">{rows(files, "project")}</ul>
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
          <ul className="source-list">{rows(globalFiles, "global")}</ul>
        )}
      </div>
    </section>
  );
}