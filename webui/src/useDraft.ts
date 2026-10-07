import { useEffect, useState } from 'react';
import { clearDraft, loadDraft, saveDraft } from './draftStorage';

export function useDraft(key: string, base: string) {
  const storageKey = `novelwb.draft.${key}`;
  const [text, setText] = useState(base);
  const [warning, setWarning] = useState('');
  const [savedAt, setSavedAt] = useState('');
  const [conflict, setConflict] = useState(false);

  useEffect(() => {
    setText(base); setWarning(''); setSavedAt(''); setConflict(false);
    if (!key) return;
    try {
      const saved = loadDraft(localStorage, storageKey);
      if (saved) {
        setText(saved.text);
        if (saved.persisted) {
          setSavedAt(new Date(saved.updatedAt).toLocaleTimeString('zh-CN', { hour12: false }));
        } else {
          setWarning('当前草稿仅暂存于本页，请在关闭浏览器前复制保存');
        }
        setConflict(saved.base !== base);
      }
    } catch { setWarning('无法读取本地草稿，请保留当前文字的副本'); }
  }, [storageKey, key, base]);

  const change = (next: string) => {
    setText(next);
    if (!key) return;
    try {
      if (next === base) {
        clearDraft(localStorage, storageKey); setSavedAt(''); setConflict(false);
      } else {
        const draft = saveDraft(localStorage, storageKey, next, base);
        setSavedAt(new Date(draft.updatedAt).toLocaleTimeString('zh-CN', { hour12: false }));
      }
      setWarning('');
    } catch { setWarning('本地草稿保存失败；当前文字暂存于本页，请在关闭浏览器前复制保存'); }
  };

  useEffect(() => {
    const onLeave = (event: BeforeUnloadEvent) => {
      if (warning && text !== base) { event.preventDefault(); event.returnValue = ''; }
    };
    window.addEventListener('beforeunload', onLeave);
    return () => window.removeEventListener('beforeunload', onLeave);
  }, [warning, text, base]);

  return { text, change, warning, savedAt, conflict, dirty: text !== base };
}
