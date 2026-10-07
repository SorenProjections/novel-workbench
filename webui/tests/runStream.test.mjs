import assert from 'node:assert/strict';
import { test } from 'node:test';
import { sourceModule } from './modules.mjs';
const { attachRunEvents, isTerminalEvent } = await sourceModule('runStream');
class Stream extends EventTarget { onerror = null; }

test('network disconnect keeps the subscription recoverable', () => {
  const stream = new Stream(); const delivered = []; let reconnects = 0;
  attachRunEvents(stream, ['step', 'error'], (...event) => delivered.push(event), () => reconnects++);
  stream.dispatchEvent(new Event('error')); stream.onerror(new Event('error'));
  assert.equal(delivered.length, 0); assert.equal(reconnects, 1);
  stream.dispatchEvent(new MessageEvent('step', { data: '{"sequence":1,"title":"恢复"}' }));
  assert.equal(delivered[0][1].title, '恢复');
});

test('replayed progress is delivered once while server errors remain terminal', () => {
  const stream = new Stream(); const delivered = [];
  attachRunEvents(stream, ['step', 'error'], (...event) => delivered.push(event), () => {});
  for (let i=0;i<2;i++) stream.dispatchEvent(new MessageEvent('step', {data:'{"sequence":2}'}));
  stream.dispatchEvent(new MessageEvent('error', {data:'{"sequence":3,"message":"失败"}'}));
  assert.equal(delivered.length, 2); assert.equal(delivered[1][0], 'error');
});

test('individual chapter failure does not end a continuing batch run', () => {
  assert.equal(isTerminalEvent('chapter_failed'), false);
  assert.equal(isTerminalEvent('sprout_event_failed'), false);
  for (const event of ['result','error','cancelled']) assert.equal(isTerminalEvent(event), true);
});
