import type { ApiEnvelope } from './types';

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  let payload: ApiEnvelope<T> | { detail?: string };
  try {
    payload = await response.json();
  } catch {
    throw new Error(`请求失败（HTTP ${response.status}）`);
  }
  if (!response.ok) {
    throw new Error('detail' in payload && payload.detail ? payload.detail : `请求失败（HTTP ${response.status}）`);
  }
  if ('status' in payload && payload.status !== 'ok') {
    throw new Error(payload.message || '请求失败');
  }
  return (payload as ApiEnvelope<T>).data;
}

export function streamUrl(path: string, params: Record<string, string | number | boolean>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) query.set(key, String(value));
  return `${path}?${query.toString()}`;
}

export function displayError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
