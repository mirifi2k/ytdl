const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const event = () => ({ listeners: [], addListener(fn) { this.listeners.push(fn); } });
const ports = [];
let badge;
const chrome = {
  action: {
    enable: async () => {}, disable: async () => {}, setTitle: async () => {},
    setBadgeBackgroundColor: () => {}, setBadgeText: ({ text }) => { badge = text; },
  },
  tabs: { onUpdated: event(), onActivated: event(), query: async () => [] },
  runtime: {
    id: 'test', onInstalled: event(), onStartup: event(), onMessage: event(),
    connectNative() {
      const port = {
        onMessage: event(), onDisconnect: event(), disconnected: false,
        postMessage(message) { this.message = message; },
        disconnect() { this.disconnected = true; },
      };
      ports.push(port);
      return port;
    },
  },
};
const context = vm.createContext({ chrome, importScripts: () => {}, isSupportedTrackUrl: () => true });
vm.runInContext(fs.readFileSync('extension/background.js', 'utf8'), context);
const message = (cmd, extra = {}) => new Promise(resolve => {
  chrome.runtime.onMessage.listeners[0]({ cmd, ...extra }, { id: 'test' }, resolve);
});
const tick = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  const started = await message('download', { url: 'https://youtube.com/watch?v=123', folder: 'House', root: '/tmp/My Music' });
  assert.equal(ports[0].message.root, '/tmp/My Music');
  assert.equal(started.state.running, true);
  assert.equal(badge, '↓');
  // No popup port exists: the background owns the connection independently.
  assert.equal(ports[0].disconnected, false);
  assert.equal((await message('download', { url: 'other', folder: 'House' })).ok, false);
  ports[0].onMessage.listeners[0]({ type: 'progress', line: '50%' });
  assert.match((await message('download_state')).log, /50%/);
  // Reopening/status requests use another host and cannot consume download events.
  const status = message('status', { root: '/tmp/My Music' });
  assert.equal(ports[1].message.root, '/tmp/My Music');
  ports[1].onMessage.listeners[0]({ ok: true, ytdl: true });
  assert.equal((await status).ytdl, true);
  assert.equal(ports[0].disconnected, false);
  ports[0].onMessage.listeners[0]({ ok: true, output: 'Saved track' });
  await tick();
  assert.equal((await message('download_state')).running, false);
  assert.equal((await message('download_state')).log, 'Saved track');
  assert.equal(badge, '✓');
  assert.equal(ports[0].disconnected, true);
  await message('download', { url: 'https://youtube.com/watch?v=456', folder: 'House' });
  chrome.runtime.lastError = { message: 'Host stopped' };
  ports[2].onDisconnect.listeners[0]();
  await tick();
  assert.equal((await message('download_state')).running, false);
  assert.equal((await message('download_state')).log, 'Host stopped');
  assert.equal(badge, '!');
  await message('download', { url: 'https://youtube.com/watch?v=789', folder: 'House' });
  const canceled = await message('cancel_download');
  assert.equal(canceled.state.canceling, true);
  assert.equal(canceled.state.running, true);
  assert.equal(ports[3].message.cmd, 'cancel');
  assert.equal(ports[3].disconnected, false);
  ports[3].onMessage.listeners[0]({ ok: false, canceled: true, output: 'Download canceled.' });
  await tick();
  const finished = await message('download_state');
  assert.equal(finished.running, false);
  assert.equal(finished.canceling, false);
  assert.equal(finished.canceled, true);
  assert.equal(badge, '');
  assert.equal((await message('download', { url: 'https://youtube.com/watch?v=next', folder: 'House' })).ok, true);
  console.log('Extension background lifecycle checks passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
