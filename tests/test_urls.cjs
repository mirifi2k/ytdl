const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({ URL });
vm.runInContext(fs.readFileSync('extension/urls.js', 'utf8'), context);
for (const host of ['www.youtube.com', 'music.youtube.com', 'm.youtube.com']) {
  const url = `https://${host}/playlist?list=PL123&index=4`;
  assert.equal(context.isSupportedTrackUrl(url), true);
  assert.equal(context.normalizeTrackUrl(url), 'https://www.youtube.com/playlist?list=PL123');
}
for (const url of ['https://youtube.com/playlist', 'https://youtube.com/playlist?list=',
  'https://youtube.com.evil.test/playlist?list=PL123', 'ftp://youtube.com/playlist?list=PL123',
  'https://soundcloud.com/artist/sets/album']) {
  assert.equal(context.isSupportedTrackUrl(url), false, url);
}
assert.equal(context.normalizeTrackUrl('https://music.youtube.com/watch?list=PL123&v=abc'),
  'https://www.youtube.com/watch?v=abc');
assert.equal(context.isSupportedTrackUrl('https://soundcloud.com/artist/track'), true);
console.log('URL validation and playlist normalization checks passed.');
