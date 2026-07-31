export type TrialErrorCode =
  | "TRIAL_REQUEST_INVALID"
  | "RESOURCE_NOT_FOUND"
  | "TRIAL_AUTHORIZATION_FORBIDDEN"
  | "TRIAL_AUTHORIZATION_UNAVAILABLE"
  | "TRIAL_SERVICE_UNAVAILABLE"
  | "TRIAL_INTERNAL_ERROR"
  | "TRIAL_UNSUPPORTED_CONTENT_TYPE"
  | "TRIAL_UNSAFE_FILE_NAME"
  | "TRIAL_FILE_HASH_MISMATCH"
  | "TRIAL_FILE_SIZE_EXCEEDED"
  | "TRIAL_CSV_PARSE_FAILED"
  | "TRIAL_XLSX_PARSE_FAILED"
  | "TRIAL_VALIDATION_FAILED"
  | "IMPORT_NOT_READY_FOR_COMMIT"
  | "CONFLICTING_REPLAY"
  | "CONCURRENCY_CONFLICT";

const messages: Record<TrialErrorCode, string> = {
  TRIAL_REQUEST_INVALID: "提交内容未通过校验，请检查输入后重试。",
  RESOURCE_NOT_FOUND: "资源当前不可用。",
  TRIAL_AUTHORIZATION_FORBIDDEN: "当前账号没有执行此操作的权限。",
  TRIAL_AUTHORIZATION_UNAVAILABLE: "授权服务暂不可用，请稍后重试。",
  TRIAL_SERVICE_UNAVAILABLE: "后端能力暂不可用，请稍后重试。",
  TRIAL_INTERNAL_ERROR: "服务暂时无法完成操作，请稍后重试。",
  TRIAL_UNSUPPORTED_CONTENT_TYPE: "文件类型不受支持，请选择 CSV 或 XLSX。",
  TRIAL_UNSAFE_FILE_NAME: "文件名不符合安全要求。",
  TRIAL_FILE_HASH_MISMATCH: "文件校验未通过，请重新选择文件。",
  TRIAL_FILE_SIZE_EXCEEDED: "文件超过允许大小。",
  TRIAL_CSV_PARSE_FAILED: "CSV 文件解析失败，请检查文件内容。",
  TRIAL_XLSX_PARSE_FAILED: "XLSX 文件解析失败，请检查文件内容。",
  TRIAL_VALIDATION_FAILED: "文件已解析，但存在需要处理的校验错误。",
  IMPORT_NOT_READY_FOR_COMMIT: "当前导入尚未满足提交条件。",
  CONFLICTING_REPLAY: "相同请求标识对应了不同内容。",
  CONCURRENCY_CONFLICT: "资源状态已变化，请重新读取后操作。",
};

export function trialErrorMessage(code: string | undefined, status?: number): string {
  if (code && code in messages) return messages[code as TrialErrorCode];
  if (status === 503) return messages.TRIAL_SERVICE_UNAVAILABLE;
  if (status === 404) return messages.RESOURCE_NOT_FOUND;
  if (status === 403) return messages.TRIAL_AUTHORIZATION_FORBIDDEN;
  return messages.TRIAL_INTERNAL_ERROR;
}
