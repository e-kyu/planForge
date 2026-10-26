import { Download, FileCode, Trash2 } from "lucide-react";
import type { SourceFile } from "../../../api/client";
import { fmtBytes } from "../../../shared/components/ui";
import { formatEpochSeconds } from "../../../shared/lib/format";

/** 포맷 배지 — API에 type 필드가 없어 확장자에서 도출 (설계 D6). */
const extOf = (name: string) => name.split(".").pop()?.toUpperCase() ?? "";

/** 소스 목록 표 — 프로젝트/글로벌 공용 (글로벌은 삭제 버튼 없음). */
export function SourceTable(props: {
  files: SourceFile[];
  dir: "project" | "global";
  pid: number;
  onDelete: (name: string) => void;
}) {
  const downloadHref = (dir: "project" | "global", name: string) =>
    dir === "project"
      ? `/api/projects/${props.pid}/sources/${encodeURIComponent(name)}/download`
      : `/api/sources/${encodeURIComponent(name)}/download`;

  return (
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
          {props.files.map((s) => (
            <tr key={`${props.dir}:${s.name}`}>
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
              <td className="source-meta">{formatEpochSeconds(s.mtime)}</td>
              <td>
                <span className="row-actions">
                  <a
                    className="row-dl"
                    href={downloadHref(props.dir, s.name)}
                    download
                    aria-label={`${s.name} 다운로드`}
                    title="다운로드"
                  >
                    <Download aria-hidden="true" />
                  </a>
                  {props.dir === "project" && (
                    <button
                      type="button"
                      className="row-del"
                      onClick={() => props.onDelete(s.name)}
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
}
