export type ApiErrorKind = 'aborted' | 'timeout' | 'network' | 'http' | 'invalid-response';

type ErrorMetadata = {
  status?: number;
  code?: string;
  requestId?: string;
  details?: Record<string, unknown>;
  retryable?: boolean;
};

export class ApiClientError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | undefined;
  readonly code: string | undefined;
  readonly requestId: string | undefined;
  readonly details: Readonly<Record<string, unknown>>;
  readonly retryable: boolean;

  constructor(kind: ApiErrorKind, message: string, metadata: ErrorMetadata = {}) {
    super(message);
    this.name = 'ApiClientError';
    this.kind = kind;
    this.status = metadata.status;
    this.code = metadata.code;
    this.requestId = metadata.requestId;
    this.details = metadata.details ?? {};
    this.retryable = metadata.retryable ?? false;
  }
}

export type ApiResponse<T> = { data: T; requestId: string };

type ErrorEnvelope = {
  error: { code: string; message: string; details: Record<string, unknown>; retryable: boolean };
  requestId: string;
};

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  formData?: FormData;
  signal?: AbortSignal;
  /** 由未来认证流程提供，仅驻留内存；后端约定后可调整头名称。 */
  csrfToken?: string;
  headers?: Readonly<Record<string, string>>;
  timeoutMs?: number;
};

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  return (
    isRecord(value) &&
    typeof value.requestId === 'string' &&
    isRecord(value.error) &&
    typeof value.error.code === 'string' &&
    typeof value.error.message === 'string' &&
    isRecord(value.error.details) &&
    typeof value.error.retryable === 'boolean'
  );
}

/** 所有请求走同源 /api；解码器负责运行时契约校验，不用类型断言伪装响应。 */
export async function request<T>(
  path: `/api/${string}`,
  isData: (value: unknown) => value is T,
  options: RequestOptions = {},
): Promise<ApiResponse<T>> {
  const { method = 'GET', signal, csrfToken, timeoutMs = 15_000 } = options;
  if (!path.startsWith('/api/')) {
    throw new TypeError('API 请求必须使用同源 /api/ 路径。');
  }
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new TypeError('timeoutMs 必须为有限正数。');
  }
  if (method === 'GET' && (options.body !== undefined || options.formData !== undefined)) {
    throw new TypeError('GET 请求不能携带请求体。');
  }
  if (options.body !== undefined && options.formData !== undefined) {
    throw new TypeError('请求不能同时包含 JSON 和 FormData。');
  }

  const headers = new Headers({ Accept: 'application/json', ...options.headers });
  const jsonBody = options.body === undefined ? undefined : JSON.stringify(options.body);
  const body = options.formData ?? jsonBody;
  if (jsonBody !== undefined) headers.set('Content-Type', 'application/json');
  if (method !== 'GET' && csrfToken) headers.set('X-CSRF-Token', csrfToken);

  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) abort();
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    if (controller.signal.aborted) throw new ApiClientError('aborted', '请求已取消。');
    const response = await fetch(path, {
      method,
      headers,
      ...(body === undefined ? {} : { body }),
      credentials: 'same-origin',
      redirect: 'error',
      cache: 'no-store',
      signal: controller.signal,
    });

    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new ApiClientError('invalid-response', '服务返回的内容不是有效 JSON。', {
        status: response.status,
      });
    }

    if (!response.ok) {
      if (!isErrorEnvelope(payload)) {
        throw new ApiClientError('invalid-response', '服务错误响应不符合约定格式。', {
          status: response.status,
        });
      }
      throw new ApiClientError('http', payload.error.message, {
        status: response.status,
        code: payload.error.code,
        details: payload.error.details,
        retryable: payload.error.retryable,
        requestId: payload.requestId,
      });
    }

    if (!isRecord(payload) || typeof payload.requestId !== 'string' || !isData(payload.data)) {
      throw new ApiClientError('invalid-response', '服务成功响应不符合约定格式。', {
        status: response.status,
      });
    }
    return { data: payload.data, requestId: payload.requestId };
  } catch (error: unknown) {
    if (controller.signal.aborted) {
      throw new ApiClientError(
        timedOut ? 'timeout' : 'aborted',
        timedOut ? '请求超时，请检查后端服务后重试。' : '请求已取消。',
        { retryable: timedOut },
      );
    }
    if (error instanceof ApiClientError) throw error;
    throw new ApiClientError('network', '无法连接后端，请检查网络与后端服务。', {
      retryable: true,
    });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}
