export interface SavedDraft { text: string; base: string; updatedAt: string; persisted: boolean }
export type DraftStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
const memoryDrafts = new Map<string, SavedDraft>();

export function loadDraft(storage: DraftStorage, key: string): SavedDraft | null {
  let raw: string | null;
  try { raw = storage.getItem(key); }
  catch (error) {
    const fallback = memoryDrafts.get(key);
    if (fallback) return fallback;
    throw error;
  }
  if (!raw) return memoryDrafts.get(key) || null;
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== 'object') throw new Error('本地草稿格式无效');
  const saved = value as Partial<SavedDraft>;
  if (typeof saved.text !== 'string' || typeof saved.base !== 'string') {
    throw new Error('本地草稿格式无效');
  }
  const draft = { text: saved.text, base: saved.base, updatedAt: saved.updatedAt || '', persisted: true };
  memoryDrafts.set(key, draft);
  return draft;
}

export function saveDraft(storage: DraftStorage, key: string, text: string, base: string): SavedDraft {
  const draft = { text, base, updatedAt: new Date().toISOString(), persisted: true };
  memoryDrafts.set(key, draft);
  try { storage.setItem(key, JSON.stringify(draft)); }
  catch (error) { memoryDrafts.set(key, { ...draft, persisted: false }); throw error; }
  return draft;
}

export function clearDraft(storage: DraftStorage, key: string): void {
  memoryDrafts.delete(key);
  storage.removeItem(key);
}
