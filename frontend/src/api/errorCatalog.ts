export type TrialErrorCode =
  | "TRIAL_REQUEST_INVALID"
  | "TRIAL_INPUT_NOT_SUPPORTED"
  | "AUTHORITY_NOT_FOUND"
  | "RESOURCE_NOT_FOUND"
  | "TRIAL_AUTHORIZATION_FORBIDDEN"
  | "TRIAL_AUTHORIZATION_UNAVAILABLE"
  | "TRIAL_AUTHORITY_UNAVAILABLE"
  | "EVIDENCE_CONFLICT"
  | "MARKETABLE_RETENTION_POLICY_MISSING"
  | "MARKETABLE_RETENTION_POLICY_CONFLICT"
  | "FORECAST_BLOCKED"
  | "IMPORT_PARSE_FAILED"
  | "IMPORT_VALIDATION_FAILED"
  | "IMPORT_NOT_READY_FOR_COMMIT"
  | "EXACT_REPLAY"
  | "CONFLICTING_REPLAY"
  | "LABEL_SNAPSHOT_UNAVAILABLE"
  | "QUALITY_AUTHORITY_UNAVAILABLE"
  | "QUALITY_PERSISTENCE_UNAVAILABLE"
  | "QUALITY_NOT_COMPUTABLE"
  | "PARTIAL_RESULT_REJECTED"
  | "CONCURRENCY_CONFLICT"
  | "TRIAL_SERVICE_UNAVAILABLE"
  | "TRIAL_INTERNAL_ERROR"
  | "TRIAL_UNSUPPORTED_CONTENT_TYPE"
  | "TRIAL_UNSAFE_FILE_NAME"
  | "TRIAL_FILE_HASH_MISMATCH"
  | "TRIAL_FILE_SIZE_EXCEEDED"
  | "TRIAL_CSV_PARSE_FAILED"
  | "TRIAL_XLSX_PARSE_FAILED"
  | "TRIAL_VALIDATION_FAILED"
  | "TRIAL_RESPONSE_CONTRACT_INVALID";

const messages: Record<TrialErrorCode, string> = {
  TRIAL_REQUEST_INVALID: "提交内容未通过校验，请检查输入后重试。",
  TRIAL_INPUT_NOT_SUPPORTED: "当前输入组合不受支持，请按服务端提供的范围选择。",
  AUTHORITY_NOT_FOUND: "输入范围当前不可用。",
  RESOURCE_NOT_FOUND: "资源当前不可用。",
  TRIAL_AUTHORIZATION_FORBIDDEN: "当前账号没有执行此操作的权限。",
  TRIAL_AUTHORIZATION_UNAVAILABLE: "授权服务暂不可用，请稍后重试。",
  TRIAL_AUTHORITY_UNAVAILABLE: "输入权威暂不可用，请稍后重试。",
  EVIDENCE_CONFLICT: "服务端证据存在冲突，已停止展示受影响结果。",
  MARKETABLE_RETENTION_POLICY_MISSING: "预测策略暂不可用，请稍后重试。",
  MARKETABLE_RETENTION_POLICY_CONFLICT: "预测策略证据存在冲突，无法生成结果。",
  FORECAST_BLOCKED: "预测被服务端证据阻断，未生成可展示结果。",
  IMPORT_PARSE_FAILED: "文件解析失败，请检查文件格式。",
  IMPORT_VALIDATION_FAILED: "文件校验失败，请查看服务端返回的错误行。",
  IMPORT_NOT_READY_FOR_COMMIT: "当前导入尚未满足提交条件。",
  EXACT_REPLAY: "请求已按原结果重放。",
  CONFLICTING_REPLAY: "相同请求标识对应了不同内容。",
  LABEL_SNAPSHOT_UNAVAILABLE: "标签快照暂不可用，请稍后重试。",
  QUALITY_AUTHORITY_UNAVAILABLE: "质量所需的历史权威暂不可用，请稍后重试。",
  QUALITY_PERSISTENCE_UNAVAILABLE: "质量报告暂时无法读取，请稍后重试。",
  QUALITY_NOT_COMPUTABLE: "质量指标当前不可计算。",
  PARTIAL_RESULT_REJECTED: "服务端返回了不完整结果，已停止展示。",
  CONCURRENCY_CONFLICT: "资源状态已变化，请重新读取后操作。",
  TRIAL_SERVICE_UNAVAILABLE: "后端能力暂不可用，请稍后重试。",
  TRIAL_INTERNAL_ERROR: "服务暂时无法完成操作，请稍后重试。",
  TRIAL_RESPONSE_CONTRACT_INVALID: "服务端返回格式异常，已停止展示本次结果。",
  TRIAL_UNSUPPORTED_CONTENT_TYPE: "文件类型不受支持，请选择 CSV 或 XLSX。",
  TRIAL_UNSAFE_FILE_NAME: "文件名不符合安全要求。",
  TRIAL_FILE_HASH_MISMATCH: "文件校验未通过，请重新选择文件。",
  TRIAL_FILE_SIZE_EXCEEDED: "文件超过允许大小。",
  TRIAL_CSV_PARSE_FAILED: "CSV 文件解析失败，请检查文件内容。",
  TRIAL_XLSX_PARSE_FAILED: "XLSX 文件解析失败，请检查文件内容。",
  TRIAL_VALIDATION_FAILED: "文件已解析，但存在需要处理的校验错误。",
};

export function trialErrorMessage(code: string | undefined, status?: number): string {
  if (code && code in messages) return messages[code as TrialErrorCode];
  if (status === 422) return messages.TRIAL_REQUEST_INVALID;
  if (status === 409) return messages.EVIDENCE_CONFLICT;
  if (status === 503) return messages.TRIAL_SERVICE_UNAVAILABLE;
  if (status === 404) return messages.RESOURCE_NOT_FOUND;
  if (status === 403) return messages.TRIAL_AUTHORIZATION_FORBIDDEN;
  return messages.TRIAL_INTERNAL_ERROR;
}
