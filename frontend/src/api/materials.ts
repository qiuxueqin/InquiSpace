import { isRecord, request } from './client';

export type SourceView = {
  id: string;
  taskId: string;
  fileName: string;
  fileType: 'pdf' | 'txt';
  byteSize: number;
  sha256: string;
  status: 'uploaded' | 'parsing' | 'ready' | 'failed';
  pageCount: number | null;
  totalLines: number | null;
  parseError: { code?: string; message?: string } | null;
  warnings: unknown[];
  createdAt: string;
};

export type EvidenceView = {
  id: string;
  sourceId: string;
  text: string;
  pageNo: number | null;
  paragraphNo: number;
  startLine: number | null;
  endLine: number | null;
  disputed: boolean;
  sourceLabel: string;
};

export type TextLinesView = {
  sourceId: string;
  totalLines: number;
  startLine: number;
  lines: string[];
};

export type ParseRunView = {
  id: string;
  kind: string;
  status: 'running' | 'waiting_confirmation' | 'completed' | 'failed' | 'cancelled';
  displayMessage: string;
  error: { code: string; message: string; retryable: boolean } | null;
};

export type UploadSourceResult = {
  source: SourceView;
  run: ParseRunView;
  revision: number;
};

export function isSourceView(value: unknown): value is SourceView {
  return isRecord(value) && typeof value.id === 'string' && typeof value.taskId === 'string'
    && typeof value.fileName === 'string' && (value.fileType === 'pdf' || value.fileType === 'txt')
    && typeof value.byteSize === 'number' && typeof value.sha256 === 'string'
    && ['uploaded', 'parsing', 'ready', 'failed'].includes(String(value.status));
}

export function isEvidenceView(value: unknown): value is EvidenceView {
  return isRecord(value) && typeof value.id === 'string' && typeof value.sourceId === 'string'
    && typeof value.text === 'string' && typeof value.paragraphNo === 'number'
    && typeof value.sourceLabel === 'string';
}

export function isTextLinesView(value: unknown): value is TextLinesView {
  return isRecord(value) && typeof value.sourceId === 'string'
    && typeof value.totalLines === 'number' && typeof value.startLine === 'number'
    && Array.isArray(value.lines) && value.lines.every(line => typeof line === 'string');
}

function isParseRunView(value: unknown): value is ParseRunView {
  return isRecord(value) && typeof value.id === 'string' && typeof value.kind === 'string'
    && typeof value.status === 'string' && typeof value.displayMessage === 'string';
}

function isUploadSourceResult(value: unknown): value is UploadSourceResult {
  return isRecord(value) && isSourceView(value.source) && isParseRunView(value.run)
    && Number.isInteger(value.revision);
}

function isSourceList(value: unknown): value is SourceView[] {
  return Array.isArray(value) && value.every(isSourceView);
}

function isDetached(value: unknown): value is { detached: boolean; revision: number } {
  return isRecord(value) && value.detached === true && Number.isInteger(value.revision);
}

export function uploadSource(
  versionId: string,
  file: File,
  revision: number,
  csrfToken: string,
  signal?: AbortSignal,
) {
  const formData = new FormData();
  formData.set('file', file);
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/sources`, isUploadSourceResult, {
    method: 'POST',
    formData,
    csrfToken,
    headers: { 'If-Match': `"rev-${revision}"` },
    timeoutMs: 30_000,
    ...(signal ? { signal } : {}),
  });
}

export function listSources(versionId: string, signal?: AbortSignal) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/sources`, isSourceList, signal ? { signal } : {});
}

export function getSource(sourceId: string, signal?: AbortSignal) {
  return request(`/api/v1/sources/${encodeURIComponent(sourceId)}`, isSourceView, signal ? { signal } : {});
}

export function getParseRun(runId: string, signal?: AbortSignal) {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}`, isParseRunView, signal ? { signal } : {});
}

export function detachSource(
  versionId: string,
  sourceId: string,
  revision: number,
  csrfToken: string,
  signal?: AbortSignal,
) {
  return request(`/api/v1/versions/${encodeURIComponent(versionId)}/sources/${encodeURIComponent(sourceId)}`, isDetached, {
    method: 'DELETE',
    csrfToken,
    headers: { 'If-Match': `"rev-${revision}"` },
    ...(signal ? { signal } : {}),
  });
}
