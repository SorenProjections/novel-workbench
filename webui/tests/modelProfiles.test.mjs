import assert from 'node:assert/strict';
import { test } from 'node:test';
import { sourceModule } from './modules.mjs';
const { newDraft, profileDraft, profileBody } = await sourceModule('modelProfiles');

test('editing a saved profile never invents a masked key or resubmits metadata', () => {
  const draft = profileDraft({ ...newDraft(), id: 'saved', has_api_key: true });
  const payload = profileBody(draft, 3);
  assert.equal(draft.api_key, '');
  assert.equal('api_key' in payload, false);
  assert.equal('has_api_key' in payload, false);
  assert.equal('id' in payload, false);
  assert.equal(payload.revision, 3);
});

test('blank means keep while clear is an explicit separate operation', () => {
  const payload = profileBody({ ...newDraft(), api_key: '   ', clear_api_key: true }, 4);
  assert.equal(payload.clear_api_key, true);
  assert.equal('api_key' in payload, false);
  assert.equal(profileBody({ ...newDraft(), api_key: ' test-key ' }, 5).api_key, 'test-key');
});

test('a provider preset resets keys and provider-specific options', () => {
  const previous = { ...newDraft(), api_key: 'test-key', thinking: 'enabled' };
  const next = newDraft(3);
  assert.equal(previous.api_key, 'test-key');
  assert.equal(next.api_key, '');
  assert.equal(next.protocol, 'anthropic');
  assert.equal(next.send_temperature, false);
});
