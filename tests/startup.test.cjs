const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

async function boot(fetch) {
  const elements = new Map();
  const document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, {
        disabled: true, hidden: false, textContent: '',
        listeners: {}, addEventListener(event, handler) { this.listeners[event] = handler; },
      });
      return elements.get(selector);
    },
    querySelectorAll() { return []; },
  };
  vm.runInNewContext(fs.readFileSync('static/app.js', 'utf8'), {
    document, fetch, AbortSignal,
    setTimeout(callback) { callback(); },
  });
  for (let index = 0; index < 40; index++) await new Promise(setImmediate);
  return elements;
}
const healthy = () => ({ ok: true, json: async () => ({ status: 'ok' }) });

test('page load immediately checks health and enables conversion', async () => {
  let calls = 0;
  const elements = await boot(async url => {
    assert.equal(url, '/health'); calls++; return healthy();
  });
  assert.equal(calls, 1);
  assert.equal(elements.get('#convert').disabled, false);
  assert.equal(elements.get('#connection-text').textContent, 'Ready');
});
test('startup retries transient failures', async () => {
  let calls = 0;
  const elements = await boot(async () => {
    if (++calls < 3) throw new Error('Starting');
    return healthy();
  });
  assert.equal(calls, 3);
  assert.equal(elements.get('#convert').disabled, false);
});
test('startup retries are bounded and offer manual retry', async () => {
  let calls = 0;
  const elements = await boot(async () => {
    if (++calls <= 12) throw new Error('Offline');
    return healthy();
  });
  assert.equal(calls, 12);
  assert.equal(elements.get('#convert').disabled, true);
  assert.equal(elements.get('#connection-retry').hidden, false);
  await elements.get('#connection-retry').listeners.click();
  assert.equal(calls, 13);
  assert.equal(elements.get('#convert').disabled, false);
});
