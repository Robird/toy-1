// Real file:// Chromium tests. Speech callbacks are controlled; audible output needs a device check.
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const vm = require('node:vm');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const game = require('../word-adventure-game.js');
const url = pathToFileURL(path.resolve(__dirname, '../word-adventure.html')).href;
const wordSandbox = { window: {} };
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, '../word-adventure-words.js'), 'utf8'), wordSandbox);
const realWords = wordSandbox.window.WORD_ADVENTURE_WORDS;
let browser;
before(async () => {
  browser = await chromium.launch({ headless: true,
    ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}) });
});
after(async () => { await browser?.close(); });

const seed = (overrides = {}) => ({ version: 1, score: 10, buffRemaining: 0, untilBoss: 0,
  history: ['bike-01', 'dog-01', 'sun-01'].map((wordId, i) => ({ wordId, kind: 'normal', endedAt: i, outcome: 'correct' })),
  ...overrides });

async function open(t, options = {}) {
  const context = await browser.newContext({ viewport: { width: 1080, height: 1000 } });
  await context.addInitScript(({ raw, legacy, unsupported, failSave, timeout, initialRandom }) => {
    if (!sessionStorage.getItem('boss-test-seeded')) {
      localStorage.clear();
      if (raw !== null) localStorage.setItem('word-adventure-progress-v1', raw);
      if (legacy !== null) localStorage.setItem('word-adventure-score-v1', legacy);
      sessionStorage.setItem('boss-test-seeded', '1');
    }
    window.__writes = [];
    const originalSet = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (this === localStorage) {
        window.__writes.push({ key, value });
        if (failSave) throw new DOMException('full', 'QuotaExceededError');
      }
      return originalSet.call(this, key, value);
    };
    window.__rng = [initialRandom];
    Math.random = () => window.__rng.shift() ?? 0;
    const nativeTimeout = window.setTimeout.bind(window);
    // Keep asynchronous boundaries but shorten animation and speech gaps, not the watchdog.
    window.setTimeout = (fn, ms, ...args) => nativeTimeout(fn,
      [100, 240, 380, 680, 1000].includes(ms) ? 8 : ms === 10000 && timeout ? 100 : ms, ...args);
    Object.defineProperty(window, 'AudioContext', { value: undefined, configurable: true });
    Object.defineProperty(window, 'webkitAudioContext', { value: undefined, configurable: true });
    if (unsupported) {
      Object.defineProperty(window, 'speechSynthesis', { value: undefined, configurable: true });
      return;
    }
    window.__speech = { items: [], active: null };
    class Utterance { constructor(text) { this.text = text; } }
    const synth = {
      getVoices: () => [], addEventListener() {}, cancel() {},
      speak(utterance) {
        window.__speech.items.push(utterance); window.__speech.active = utterance;
        nativeTimeout(() => {
          utterance.__started = true; utterance.onstart?.();
          const activeBoss = document.getElementById('lesson').classList.contains('boss') &&
            document.getElementById('completion').hidden;
          if (!activeBoss || utterance.lang === 'zh-CN') nativeTimeout(() => utterance.onend?.(), 1);
        }, 0);
      }
    };
    Object.defineProperty(window, 'SpeechSynthesisUtterance', { value: Utterance, configurable: true });
    Object.defineProperty(window, 'speechSynthesis', { value: synth, configurable: true });
  }, { raw: options.raw === undefined ? JSON.stringify(options.progress || seed()) : options.raw,
    legacy: options.legacy ?? null, unsupported: !!options.unsupported,
    failSave: !!options.failSave, timeout: !!options.timeout, initialRandom: options.initialRandom || 0 });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  t.after(async () => { await context.close(); assert.deepEqual(errors, [], 'no browser script errors'); });
  await page.goto(url + (options.query || ''));
  return page;
}

async function stored(page) {
  return page.evaluate(() => JSON.parse(localStorage.getItem('word-adventure-progress-v1')));
}

async function enterBoss(page, kind = 'recall') {
  await page.evaluate(kind => {
    const pool = window.WORD_ADVENTURE_WORDS;
    const target = pool.find(w => w.id === 'bike-01');
    const images = pool.filter(w => w.illustration);
    const distractors = images.filter(w => w.illustration !== target.illustration);
    window.__rng = [0, {image: 0, partial: .4, recall: .9}[kind],
      (distractors.findIndex(w => w.id === 'dog-01') + .1) / distractors.length,
      (images.findIndex(w => w.id === 'bicycle-01') + .1) / images.length, 0, 0];
    if (kind !== 'image') window.__rng = [0, {partial: .4, recall: .9}[kind], .4, .4];
  }, kind);
  await page.keyboard.type('cat');
  await page.waitForFunction(() => document.getElementById('lesson').classList.contains('boss'));
  await page.waitForFunction(() => window.__speech?.active?.text === 'bike' && window.__speech.active.__started);
  assert.match(await page.locator('#task-title').innerText(), {image:/听音找图/, partial:/补上字母/, recall:/自己拼单词/}[kind]);
}

async function hear(page) {
  await page.evaluate(() => window.__speech.active.onend());
}

async function completeNormal(page) {
  await page.waitForFunction(() => !document.getElementById('lesson').classList.contains('boss') &&
    document.getElementById('completion').hidden);
  const letters = await page.locator('#slots .slot').allTextContents();
  await page.keyboard.type(letters.join('').toLowerCase());
}

test('recall: no leaked spelling, unrestricted editing, heard qualification and one settlement', async t => {
  const page = await open(t);
  await enterBoss(page);
  assert.equal(await page.locator('#keyboard .key[data-letter]:enabled').count(), 26);
  assert.deepEqual(await page.locator('#slots .slot').allTextContents(), ['·', '·', '·', '·']);
  for (const id of ['instruction', 'audio-state', 'feedback']) assert.doesNotMatch(await page.locator('#' + id).innerText(), /bike/i);
  assert.ok((await page.locator('#slots .slot').evaluateAll(slots => slots.map(s => s.getAttribute('aria-label')))).every(label => !/[BIKE]/.test(label)));
  await page.keyboard.type('xxxx');
  assert.deepEqual(await page.locator('#slots .slot').allTextContents(), ['X', 'X', 'X', 'X']);
  assert.equal(await page.locator('#submit').isDisabled(), true);
  for (let i = 0; i < 4; i++) await page.keyboard.press('Backspace');
  await page.keyboard.type('bike');
  await page.locator('#letter-case').click();
  assert.deepEqual(await page.locator('#slots .slot').allTextContents(), ['b', 'i', 'k', 'e']);
  await hear(page);
  assert.equal(await page.locator('#submit').isEnabled(), true);
  const before = await stored(page);
  await page.locator('[data-letter="E"]').focus();
  await page.keyboard.press('Enter');
  await page.evaluate(() => { document.getElementById('submit').click(); window.__speech.items.forEach(item => item.onend?.()); });
  const after = await stored(page);
  assert.equal(after.score, before.score);
  assert.equal(after.buffRemaining, 5);
  assert.equal(after.history.length, before.history.length + 1);
  assert.deepEqual(after.history.at(-1).kind, 'recall');
  assert.equal(after.history.at(-1).outcome, 'correct');
  assert.equal(await page.locator('#buff').isVisible(), true);
  await page.reload();
  assert.equal((await stored(page)).buffRemaining, 5);
  assert.equal(await page.locator('#lesson').evaluate(el => el.classList.contains('boss')), false);
  assert.equal(await page.locator('#word-points').innerText(), '1 分');
});

test('partial: stable mask, hidden letters only, assisted follow-along cannot grant Buff', async t => {
  const page = await open(t);
  await enterBoss(page, 'partial');
  const mask = await page.locator('#slots .slot').allTextContents();
  assert.equal(mask.filter(s => s === '·').length, 2);
  assert.equal(mask.filter(s => s !== '·').length, 2);
  const missing = [...'BIKE'].filter((_, i) => mask[i] === '·').join('');
  await page.keyboard.type(missing.slice(0, 1));
  await hear(page);
  assert.equal(await page.locator('#submit').isDisabled(), true);
  await page.keyboard.type(missing.slice(1));
  assert.equal(await page.locator('#submit').isEnabled(), true);
  await page.locator('#listen').click();
  assert.equal(await page.locator('#submit').isEnabled(), true);
  await page.locator('#letter-case').click();
  assert.deepEqual(await page.locator('#slots .slot').allTextContents(), [...'bike']);
  await page.locator('#answer').click();
  const assisted = await stored(page);
  assert.equal(assisted.history.at(-1).outcome, 'assisted');
  assert.equal(assisted.history.at(-1).missingCount, 2);
  assert.equal(assisted.buffRemaining, 0);
  await page.locator('#practice').click();
  await page.keyboard.type('bike');
  assert.match(await page.locator('#feedback').innerText(), /跟练完成/);
  assert.deepEqual(await stored(page), assisted);
});

test('wrong first submission stays wrong; partial independent success uses hidden sequence', async t => {
  const page = await open(t);
  await enterBoss(page);
  await hear(page);
  await page.keyboard.type('xxxx');
  await page.locator('#submit').click();
  const failed = await stored(page);
  assert.equal(failed.history.at(-1).outcome, 'wrong');
  assert.equal(failed.buffRemaining, 0);
  await page.keyboard.type('bike');
  await page.evaluate(() => document.getElementById('submit').click());
  assert.deepEqual(await stored(page), failed);
  const partial = await open(t);
  await enterBoss(partial, 'partial');
  const mask = await partial.locator('#slots .slot').allTextContents();
  await partial.keyboard.type([...'BIKE'].filter((_, i) => mask[i] === '·').join('').toLowerCase());
  await hear(partial);
  await partial.locator('#submit').click();
  assert.equal((await stored(partial)).history.at(-1).outcome, 'correct');
  assert.equal((await stored(partial)).buffRemaining, 5);
});

test('image: both identical emojis succeed; a different emoji fails; titles and audio hide target', async t => {
  for (const selected of [0, 1, 2]) {
    const page = await open(t);
    await enterBoss(page, 'image');
    const options = page.locator('#image-options button');
    const emojis = await options.evaluateAll(items => items.map(el => el.dataset.emoji));
    assert.equal(emojis.filter(e => e === '🚲').length, 2);
    assert.equal(emojis.filter(e => e === '🐶').length, 1);
    const matchingNames = await options.evaluateAll(items => items.filter(el => el.dataset.emoji === '🚲').map(el => el.getAttribute('aria-label')));
    assert.equal(matchingNames[0], matchingNames[1]);
    for (const id of ['task-title', 'instruction', 'audio-state', 'feedback', 'friend-caption']) {
      assert.doesNotMatch(await page.locator('#' + id).innerText(), /bike|自行车/i);
    }
    assert.equal(await page.locator('#keyboard-area').isVisible(), false);
    await options.nth(selected).click();
    assert.equal(await page.locator('#submit').isDisabled(), true);
    await hear(page);
    await page.locator('#submit').click();
    const progress = await stored(page);
    assert.equal(progress.history.at(-1).outcome, emojis[selected] === '🚲' ? 'correct' : 'wrong');
    assert.equal(progress.buffRemaining, emojis[selected] === '🚲' ? 5 : 0);
  }
});

test('blur cancellation and old callbacks do not qualify; failed replay preserves acquired qualification', async t => {
  const page = await open(t);
  await enterBoss(page);
  await page.keyboard.type('bike');
  await page.evaluate(() => {
    window.__old = window.__speech.active;
    window.dispatchEvent(new Event('blur'));
    window.__old.onend(); window.__old.onerror({ error: 'failed' });
  });
  assert.equal(await page.locator('#submit').isDisabled(), true);
  const before = await stored(page);
  await page.locator('#listen').click();
  await page.waitForFunction(() => window.__speech.active.__started);
  await hear(page);
  assert.equal(await page.locator('#submit').isEnabled(), true);
  await page.locator('#listen').click();
  await page.evaluate(() => window.__speech.active.onerror({ error: 'failed' }));
  assert.equal(await page.locator('#submit').isEnabled(), true);
  assert.equal(await page.locator('#audio-continue').isVisible(), false);
  assert.deepEqual(await stored(page), before);
});

test('initial playback failure, timeout, voluntary skip and unavailable are distinct', async t => {
  for (const mode of ['not-allowed', 'timeout', 'skip']) {
    const page = await open(t, { timeout: mode === 'timeout' });
    await enterBoss(page);
    await page.keyboard.type('bike');
    const before = await stored(page);
    if (mode === 'not-allowed') await page.evaluate(() => window.__speech.active.onerror({ error: 'not-allowed' }));
    if (mode !== 'skip') {
      await page.locator('#audio-continue').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#submit').isDisabled(), true);
      assert.deepEqual(await stored(page), before);
      await page.locator('#audio-continue').click();
    } else await page.locator('#skip').click();
    const result = await stored(page);
    assert.equal(result.history.at(-1).outcome, mode === 'skip' ? 'skipped' : 'unavailable');
    assert.equal(result.buffRemaining, 0);
    assert.equal(result.score, before.score);
  }
});

test('unsupported speech ends Boss unavailable, ordinary play remains possible', async t => {
  const page = await open(t, { unsupported: true });
  await page.keyboard.type('cat');
  await page.waitForFunction(() => document.getElementById('lesson').classList.contains('boss'));
  assert.equal((await stored(page)).history.at(-1).outcome, 'unavailable');
  await page.locator('#next').click();
  assert.equal(await page.locator('#lesson').evaluate(el => el.classList.contains('boss')), false);
});

test('five ordinary rewards are doubled, sixth is base, unfinished reload costs nothing', async t => {
  const page = await open(t, { progress: seed({ history: [], buffRemaining: 5, untilBoss: 8 }) });
  await page.keyboard.type('c');
  await page.reload();
  assert.equal((await stored(page)).buffRemaining, 5);
  for (let i = 0; i < 6; i++) {
    await completeNormal(page);
    const current = await stored(page);
    assert.equal(current.score, 10 + Math.min(i + 1, 5) + (i === 5 ? .5 : 0));
    assert.equal(current.buffRemaining, Math.max(0, 4 - i));
    assert.equal(current.untilBoss, i < 5 ? 8 : 7);
    assert.equal(current.history.length, i + 1);
  }
});

test('legacy score migrates once; corrupt new progress is preserved and blocks play', async t => {
  const migration = await open(t, { raw: null, legacy: '7.5' });
  assert.equal((await stored(migration)).score, 7.5);
  await migration.keyboard.type('cat');
  assert.equal((await stored(migration)).score, 8);
  assert.equal(await migration.evaluate(() => localStorage.getItem('word-adventure-score-v1')), '7.5');
  for (const raw of ['{', JSON.stringify(seed({ version: 2 })), JSON.stringify(seed({ score: -1 })),
    JSON.stringify(seed({ buffRemaining: 6 })), JSON.stringify(seed({ untilBoss: 13 }))]) {
    const page = await open(t, { raw, legacy: '99' });
    assert.equal(await page.locator('#storage-notice').isVisible(), true);
    assert.equal(await page.locator('#lesson').isVisible(), false);
    await page.keyboard.type('cat');
    assert.equal(await page.evaluate(() => localStorage.getItem('word-adventure-progress-v1')), raw);
    assert.deepEqual(await page.evaluate(() => window.__writes), []);
  }
});

test('save failure preserves in-memory scoring and visibly reports unsaved progress', async t => {
  const initial = seed({ history: [], buffRemaining: 1, untilBoss: 8 });
  const page = await open(t, { progress: initial, failSave: true });
  await page.keyboard.type('cat');
  assert.equal(await page.locator('#score').innerText(), '11');
  assert.equal(await page.locator('#buff').isVisible(), false);
  assert.match(await page.locator('#storage-notice').innerText(), /没能保存.*保持页面打开/);
  assert.deepEqual(await stored(page), initial);
  const writes = await page.evaluate(() => window.__writes);
  assert.equal(writes.length, 1);
  const pending = JSON.parse(writes[0].value);
  assert.equal(pending.score, 11);
  assert.equal(pending.buffRemaining, 0);
  assert.equal(pending.history.length, 1);
});

test('ordinary URL difficulty still works; mobile Boss fits screen and screenshots can be captured', async t => {
  const ordinary = await open(t, { progress: seed({ untilBoss: 8 }), query: '?distractorCount=4&showSpelling=false' });
  assert.equal(await ordinary.locator('#keyboard .key[data-letter]:enabled').count(), 7);
  assert.deepEqual(await ordinary.locator('#slots .slot').allTextContents(), ['·', '·', '·']);
  const page = await open(t);
  await enterBoss(page, 'image');
  if (process.env.BOSS_SCREENSHOT_DIR) {
    fs.mkdirSync(process.env.BOSS_SCREENSHOT_DIR, { recursive: true });
    await page.screenshot({ path: path.join(process.env.BOSS_SCREENSHOT_DIR, 'boss-desktop.png'), fullPage: true });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
  assert.equal(await page.locator('#image-options button').count(), 3);
  if (process.env.BOSS_SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.BOSS_SCREENSHOT_DIR, 'boss-mobile.png'), fullPage: true });
  for (const kind of ['partial', 'recall']) {
    const spelling = await open(t);
    await enterBoss(spelling, kind);
    await spelling.setViewportSize({ width: 390, height: 844 });
    assert.equal(await spelling.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
    if (process.env.BOSS_SCREENSHOT_DIR) {
      await spelling.screenshot({ path: path.join(process.env.BOSS_SCREENSHOT_DIR, `boss-${kind}-mobile.png`), fullPage: true });
      await spelling.keyboard.type('bike');
      await spelling.locator('#answer').click();
    }
  }
  if (process.env.BOSS_SCREENSHOT_DIR) {
    const buff = await open(t, { progress: seed({ history: [], buffRemaining: 5, untilBoss: 8 }) });
    await buff.screenshot({ path: path.join(process.env.BOSS_SCREENSHOT_DIR, 'buff-desktop.png'), fullPage: true });
  }
});

test('ordinary phrases, long words and speech overrides retain their existing behavior', async t => {
  for (const spelling of ['ICE CREAM', 'BASKETBALL', 'TV']) {
    const index = realWords.findIndex(word => word.word === spelling);
    assert.notEqual(index, -1);
    const word = realWords[index];
    const page = await open(t, { progress: seed({ history: [], untilBoss: 8 }), initialRandom: (index + .1) / realWords.length });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.locator('#slots .slot').count(), spelling.replace(/ /g, '').length);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
    if (spelling.includes(' ')) assert.equal(await page.locator('#slots .word-start').count(), 1);
    if (word.speech) {
      await page.waitForFunction(text => window.__speech.items.some(item => item.text === text), word.speech);
    }
    await page.keyboard.type(spelling.replace(/ /g, '').toLowerCase());
    assert.equal((await stored(page)).score, 10 + game.wordReward(spelling.replace(/ /g, '').length));
    assert.equal((await stored(page)).history.at(-1).wordId, word.id);
  }
});
