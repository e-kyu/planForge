import { ApiError } from "../../api/client";

/* ApiError → 화면 표시 문자열 변환 (전 feature viewmodels 공용). */
export const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : String(e));