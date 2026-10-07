export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '暂无';
  if (Array.isArray(value)) return value.length ? value.map(formatValue).join('、') : '暂无';
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    return entries.length ? entries.map(([key, item]) => `${key}：${formatValue(item)}`).join('\n') : '暂无';
  }
  return String(value);
}

export function formatNumber(value: number | undefined): string {
  return new Intl.NumberFormat('zh-CN').format(value || 0);
}

export function formatDate(value?: string): string {
  if (!value) return '时间未知';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}

export function shortFingerprint(value?: string | null): string {
  if (!value) return '暂无';
  return value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : value;
}
