import assert from 'node:assert/strict';
import { test } from 'node:test';
import { sourceModule } from './modules.mjs';
const { loadDraft, saveDraft, clearDraft } = await sourceModule('draftStorage');
function storage() {
  const values = new Map();
  return { getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
}

test('draft text and original source survive an editor reload', () => {
  const local = storage();
  saveDraft(local, 'project-a:review-1', '人工修改全文', '原始全文');
  const restored = loadDraft(local, 'project-a:review-1');
  assert.equal(restored.text, '人工修改全文');
  assert.equal(restored.base, '原始全文');
  assert.notEqual(restored.base, '服务器更新全文');
});

test('draft keys isolate projects and logical files', () => {
  const local = storage();
  saveDraft(local, 'project-a:asset-one', '甲', '旧甲');
  saveDraft(local, 'project-b:asset-one', '乙', '旧乙');
  assert.equal(loadDraft(local, 'project-a:asset-one').text, '甲');
  assert.equal(loadDraft(local, 'project-b:asset-one').text, '乙');
  assert.equal(loadDraft(local, 'project-a:asset-two'), null);
});

test('storage quota failure preserves current-page draft and exposes the error', () => {
  const blocked = { getItem() { throw new Error('blocked'); },
    setItem() { throw new Error('quota exceeded'); }, removeItem() {} };
  assert.throws(() => saveDraft(blocked, 'quota-case', '保留这一版', '旧版'), /quota exceeded/);
  assert.equal(loadDraft(blocked, 'quota-case').text, '保留这一版');
  assert.equal(loadDraft(blocked, 'quota-case').persisted, false);
});

test('restoring the saved source clears the discarded draft', () => {
  const local = storage();
  saveDraft(local, 'reset-case', '新文', '旧文');
  clearDraft(local, 'reset-case');
  assert.equal(loadDraft(local, 'reset-case'), null);
});

test('corrupted local storage cannot become an editable draft', () => {
  const local = storage();
  local.setItem('corrupt-case', '{"text":123}');
  assert.throws(() => loadDraft(local, 'corrupt-case'), /格式无效/);
});
