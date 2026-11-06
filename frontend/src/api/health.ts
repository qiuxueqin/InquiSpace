import { isRecord, request } from './client';

export type HealthData = {
  status: 'ok';
  service: 'inquispace';
  version: string;
  database: 'ok';
};

function isHealthData(value: unknown): value is HealthData {
  return (
    isRecord(value) &&
    value.status === 'ok' &&
    value.service === 'inquispace' &&
    typeof value.version === 'string' &&
    value.version.length > 0 &&
    value.database === 'ok'
  );
}

export function getHealth(signal?: AbortSignal) {
  return request('/api/v1/health', isHealthData, signal ? { signal } : {});
}
