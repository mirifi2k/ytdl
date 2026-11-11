const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let stored = '/tmp/Original Music';
let invalid = false;
let downloadState = { running: false };
const fallback = new Map();
const localStorage = {
  getItem: key => fallback.get(key) ?? null,
  setItem: (key, value) => fallback.set(key, value),
};
const requests = [];
function openPopup(withStorage = true) {
  const elements = new Map();
  function element() {
    return {
      value: '', listeners: {}, children: [],
      addEventListener(name, fn) { this.listeners[name] = fn; },
      setAttribute() {},
      replaceChildren() { this.children = []; },
      appendChild(child) { this.children.push(child); },
    };
  }
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    },
    createElement: element,
  };
  const chrome = {
    storage: { local: {
      get: async () => ({ downloadRoot: stored }),
      set: async ({ downloadRoot }) => { stored = downloadRoot; },
    } },
    tabs: { query: async () => [{ url: 'https://youtu.be/123' }] },
    runtime: { sendMessage: async (message) => {
      requests.push(message);
      if (message.cmd === 'download_state') return downloadState;
      if (message.cmd === 'cancel_download') {
        downloadState = { ...downloadState, canceling: true };
        return { ok: true, state: downloadState };
      }
      if (message.cmd === 'status') return { ok: true, ytdl: true };
      if (message.cmd === 'list_folders') return invalid
        ? { ok: false, error: 'Missing folder' }
        : { ok: true, root: message.root, folders: ['.', 'House/Deep'] };
    } },
  };
  if (!withStorage) delete chrome.storage;
  vm.runInNewContext(fs.readFileSync('extension/popup.js', 'utf8'), {
    document, chrome, localStorage, setInterval: () => {},
    isSupportedTrackUrl: () => true, normalizeTrackUrl: url => url,
  });
  return id => document.getElementById(id);
}
const tick = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  let el = openPopup();
  await tick();
  assert.equal(el('root').value, stored);
  assert.equal(el('folders').children.length, 2);
  el('root').value = '/tmp/New Music';
  await el('root-form').listeners.submit({ preventDefault() {} });
  assert.equal(stored, '/tmp/New Music');
  assert.equal(requests.at(-1).root, stored);
  el = openPopup();
  await tick();
  assert.equal(el('root').value, '/tmp/New Music');
  invalid = true;
  el('root').value = '/missing';
  await el('root-form').listeners.submit({ preventDefault() {} });
  assert.equal(stored, '/tmp/New Music');
  assert.equal(el('download').disabled, true);
  assert.equal(el('status-block').textContent, 'Missing folder');
  invalid = false;
  el = openPopup(false);
  await tick();
  assert.equal(el('root').value, '/tmp/New Music');
  el('root').value = '/tmp/Fallback Music';
  await el('root-form').listeners.submit({ preventDefault() {} });
  el = openPopup(false);
  await tick();
  assert.equal(el('root').value, '/tmp/Fallback Music');
  downloadState = { running: true, url: 'https://youtu.be/123', folder: '.', log: 'Downloading' };
  el = openPopup();
  await tick();
  assert.equal(el('cancel').hidden, false);
  assert.equal(el('cancel').disabled, false);
  await el('cancel').listeners.click();
  assert.equal(el('cancel').textContent, 'Canceling…');
  assert.equal(el('cancel').disabled, true);
  assert.equal(el('download').disabled, true);
  downloadState = { ...downloadState, running: false, canceling: false, canceled: true, log: 'Download canceled.' };
  el = openPopup();
  await tick();
  assert.equal(el('cancel').hidden, true);
  assert.equal(el('download').disabled, false);
  assert.equal(el('folders').children.length, 2);
  stored = undefined;
  el = openPopup();
  await tick();
  assert.equal(el('root').value, '/tmp/Fallback Music');
  console.log('Popup folder persistence checks passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
