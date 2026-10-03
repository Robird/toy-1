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
  const context = await browser.newContext({ viewport: options.touch ? { width: 390, height: 844 } : { width: 1080, height: 1000 },
    hasTouch: !!options.touch });
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
      [100, 240, 380, 680, 1000].includes(ms) ? 8 : ms === 10000 &&
        (timeout || (window.__speech?.fastTimeout && window.__speech.constructing?.lang === 'zh-CN')) ? 100 : ms, ...args);
    Object.defineProperty(window, 'AudioContext', { value: undefined, configurable: true });
    Object.defineProperty(window, 'webkitAudioContext', { value: undefined, configurable: true });
    if (unsupported) {
      Object.defineProperty(window, 'speechSynthesis', { value: undefined, configurable: true });
      return;
    }
    window.__speech = { items: [], active: null, chineseMode: 'end', fastTimeout: false };
    class Utterance { constructor(text) { this.text = text; window.__speech.constructing = this; } }
    const synth = {
      getVoices: () => [], addEventListener() {}, cancel() {},
      speak(utterance) {
        window.__speech.items.push(utterance); window.__speech.active = utterance;
        const fault = window.__speech.failText?.[utterance.text];
        if (fault === 'throw') throw new Error('mock synthesis failure for ' + utterance.text);
        nativeTimeout(() => {
          if (window.__speech.suppressStart) return;
          utterance.__started = true; utterance.onstart?.();
          if (fault === 'error') { nativeTimeout(() => utterance.onerror?.({ error: 'failed' }), 1); return; }
          const activeBoss = document.getElementById('lesson').classList.contains('boss') &&
            document.getElementById('completion').hidden;
          if (!activeBoss) nativeTimeout(() => utterance.onend?.(), 1);
          else if (utterance.lang === 'zh-CN') {
            const mode = window.__speech.chineseMode;
            if (mode === 'end') nativeTimeout(() => utterance.onend?.(), 1);
            else if (mode !== 'hold') nativeTimeout(() => utterance.onerror?.({ error: mode }), 1);
          }
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

async function enterBoss(page, kind = 'recall', chineseMode = 'end') {
  await page.evaluate(({ kind, chineseMode }) => {
    window.__speech.chineseMode = chineseMode;
    window.__speech.fastTimeout = chineseMode === 'hold';
    const pool = window.WORD_ADVENTURE_WORDS;
    const target = pool.find(w => w.id === 'bike-01');
    const images = pool.filter(w => w.illustration);
    const distractors = images.filter(w => w.illustration !== target.illustration);
    window.__rng = [0, {image: 0, partial: .4, recall: .9}[kind],
      (distractors.findIndex(w => w.id === 'dog-01') + .1) / distractors.length,
      (images.findIndex(w => w.id === 'bicycle-01') + .1) / images.length, 0, 0];
    if (kind !== 'image') window.__rng = [0, {partial: .4, recall: .9}[kind], .4, .4];
  }, { kind, chineseMode });
  await page.keyboard.type('cat');
  await page.waitForFunction(() => document.getElementById('lesson').classList.contains('boss'));
  await page.waitForFunction(() => window.__speech?.active?.text === 'bike' && window.__speech.active.__started);
  assert.match(await page.locator('#task-title').innerText(), {image:/听音找图/, partial:/补上字母/, recall:/自己拼单词/}[kind]);
}

async function help(page, choice, source = '#help') {
  await page.locator(source).click();
  await page.locator('#help-dialog').waitFor({ state: 'visible' });
  if (choice) await page.locator('#help-' + choice).click();
}

async function confirmHelp(page, choice, source) {
  await help(page, choice, source);
  await page.locator('#help-confirm').click();
}

async function challengeSnapshot(page) {
  return page.evaluate(() => ({
    progress: localStorage.getItem('word-adventure-progress-v1'), writes: window.__writes.length,
    slots: [...document.querySelectorAll('#slots .slot')].map(el => [el.textContent, el.classList.contains('given')]),
    images: [...document.querySelectorAll('#image-options button')].map(el => [el.dataset.emoji, el.className, el.getAttribute('aria-pressed')]),
    title: document.getElementById('task-title').textContent,
    letterCase: document.querySelector('#keyboard [data-letter]')?.textContent
  }));
}

async function assertOrdinaryExit(page, before, outcome, speechStart) {
  await page.waitForFunction(() => !document.getElementById('lesson').classList.contains('boss'));
  const progress = await stored(page);
  assert.equal(progress.history.length, before.history.length + 1);
  assert.equal(progress.history.at(-1).outcome, outcome);
  assert.equal(progress.score, before.score);
  assert.equal(progress.buffRemaining, before.buffRemaining);
  assert.ok(progress.untilBoss >= 8 && progress.untilBoss <= 12);
  assert.equal(await page.locator('#completion').isVisible(), false);
  await page.waitForTimeout(40);
  const spoken = await page.evaluate(start => window.__speech.items.slice(start).map(item => item.text), speechStart);
  assert.ok(!spoken.some(text => /^bike$|自行车/i.test(text)), 'exit must not speak the Boss answer');
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
  await confirmHelp(page, 'learn');
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
  for (const mode of ['not-allowed', 'failed', 'language-unavailable', 'voice-unavailable', 'timeout', 'skip']) {
    const page = await open(t, { timeout: mode === 'timeout' });
    await enterBoss(page);
    await page.keyboard.type('bike');
    const before = await stored(page);
    if (mode !== 'timeout' && mode !== 'skip') await page.evaluate(error => window.__speech.active.onerror({ error }), mode);
    if (mode !== 'skip') {
      await page.locator('#audio-continue').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#submit').isDisabled(), true);
      assert.deepEqual(await stored(page), before);
      await help(page, null, '#audio-continue');
      assert.deepEqual(await stored(page), before, 'failure continue only opens help');
      assert.equal(await page.locator('#help-confirm').isDisabled(), true);
      await page.locator('#help-leave').click();
      await page.locator('#help-confirm').click();
    } else await confirmHelp(page, 'leave');
    const result = await stored(page);
    assert.equal(result.history.at(-1).outcome, mode === 'skip' ? 'skipped' : 'unavailable');
    assert.equal(result.buffRemaining, 0);
    assert.equal(result.score, before.score);
  }
});

test('unsupported speech ends Boss unavailable, ordinary play remains possible', async t => {
  const page = await open(t, { unsupported: true });
  await page.keyboard.type('cat');
  await page.waitForFunction(() => JSON.parse(localStorage.getItem('word-adventure-progress-v1')).history.at(-1).outcome === 'unavailable');
  assert.equal((await stored(page)).history.at(-1).outcome, 'unavailable');
  assert.equal(await page.locator('#lesson').evaluate(el => el.classList.contains('boss')), false);
  assert.equal(await page.locator('#completion').isVisible(), false);
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
      await confirmHelp(spelling, 'learn');
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

test('help exploration and return preserve recall input, partial mask, image choice and every progress write', async t => {
  for (const kind of ['recall', 'partial', 'image']) {
    const page = await open(t);
    await enterBoss(page, kind);
    await hear(page);
    if (kind === 'image') await page.locator('#image-options button').nth(1).click();
    else await page.keyboard.type(kind === 'recall' ? 'bi' : 'i');
    const before = await challengeSnapshot(page);
    const ready = await page.locator('#submit').isEnabled();
    await help(page);
    assert.equal(await page.locator('#help-confirm').isDisabled(), true);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'help-back');
    if (kind === 'image') {
      await page.evaluate(() => document.querySelectorAll('#image-options button').forEach(button => button.click()));
      assert.deepEqual(await challengeSnapshot(page), before, 'programmatic background image clicks are guarded too');
    }
    for (const choice of ['learn', 'leave', 'learn', 'leave']) {
      await page.locator('#help-' + choice).click();
      assert.equal(await page.locator('#help-confirm').isEnabled(), true);
      assert.notEqual(await page.evaluate(() => document.activeElement.id), 'help-confirm');
      assert.equal(await page.locator('#completion').isVisible(), false);
      assert.deepEqual(await challengeSnapshot(page), before);
    }
    if (kind === 'image') {
      const text = await page.locator('#help-dialog').innerText();
      assert.doesNotMatch(text, /bike|bicycle|自行车|🚲/i);
      const names = await page.locator('#help-dialog [aria-label]').evaluateAll(items => items.map(el => el.getAttribute('aria-label')).join(' '));
      assert.doesNotMatch(names, /bike|bicycle|自行车|🚲/i);
    }
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#help-dialog').isVisible(), false);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'help');
    assert.deepEqual(await challengeSnapshot(page), before);
    assert.equal(await page.locator('#submit').isEnabled(), ready, 'return preserves acquired hearing and readiness');
    await help(page);
    assert.equal(await page.locator('#help-confirm').isDisabled(), true, 'choice must reset after return');
    await page.locator('#help-back').click();
    assert.deepEqual(await challengeSnapshot(page), before);
  }
});

test('modal isolates keyboard, background commands, hover and blank gesture without settling', async t => {
  const page = await open(t);
  await enterBoss(page);
  await hear(page);
  await page.keyboard.type('bike');
  await page.locator('#listen').click();
  await page.waitForFunction(() => window.__speech.active.text === 'bike' && window.__speech.active.__started);
  await page.evaluate(() => {
    window.__speech.active.onerror({ error: 'not-allowed' });
    window.__speech.chineseMode = 'hold';
    window.__speech.suppressStart = true;
  });
  const before = await challengeSnapshot(page);
  await help(page);
  await page.locator('#help-learn').click();
  await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  const spoken = await page.evaluate(() => window.__speech.items.length);
  await page.keyboard.type('x');
  await page.keyboard.press('Backspace');
  await page.keyboard.press('Shift');
  await page.evaluate(() => {
    for (const id of ['listen', 'erase', 'submit', 'letter-case', 'next', 'practice', 'audio-continue']) document.getElementById(id).click();
    const key = document.querySelector('[data-letter="A"]');
    key.click(); key.dispatchEvent(new MouseEvent('mouseenter'));
  });
  const bounds = await page.locator('#help-dialog').boundingBox();
  await page.mouse.click(bounds.x + bounds.width - 8, bounds.y + bounds.height - 8);
  assert.equal(await page.evaluate(() => document.activeElement.closest('button') === null), true, 'blank click moves focus off action buttons');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Space');
  await page.mouse.click(bounds.x + bounds.width - 8, bounds.y + bounds.height - 8);
  await page.waitForTimeout(50);
  assert.deepEqual(await challengeSnapshot(page), before);
  assert.deepEqual(await page.evaluate(start => window.__speech.items.slice(start).map(item => item.text), spoken), [],
    'background gesture or hover must not restart speech');
  assert.equal(await page.locator('#help-dialog').isVisible(), true);
  assert.equal(await page.locator('#completion').isVisible(), false);
  await page.locator('#help-back').click();
  assert.equal(await page.locator('#submit').isEnabled(), true);
});

test('rapid choices, same-position double clicks, touch taps and repeated keys cannot execute a choice', async t => {
  for (const touch of [false, true]) {
    const page = await open(t, { touch });
    await enterBoss(page, 'image');
    const before = await stored(page);
    const entry = await page.locator('#help').boundingBox();
    const tap = async box => touch
      ? page.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2)
      : page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await tap(entry); await tap(entry);
    assert.equal(await page.locator('#help-dialog').isVisible(), true);
    assert.equal(await page.locator('#help-confirm').isDisabled(), true);
    for (const id of ['help-learn', 'help-leave', 'help-learn']) {
      const card = await page.locator('#' + id).boundingBox();
      const confirm = await page.locator('#help-confirm').boundingBox();
      for (const origin of [entry, card]) {
        const x = origin.x + origin.width / 2, y = origin.y + origin.height / 2;
        assert.ok(x < confirm.x || x > confirm.x + confirm.width || y < confirm.y || y > confirm.y + confirm.height,
          'execution must not occupy an entry or card click position');
      }
      await tap(card); await tap(card);
      if (!touch) await page.locator('#' + id).dblclick();
      await page.locator('#' + id).focus();
      await page.keyboard.down('Enter'); await page.keyboard.down('Enter'); await page.keyboard.up('Enter');
      await page.keyboard.down('Space'); await page.keyboard.down('Space'); await page.keyboard.up('Space');
      assert.deepEqual(await stored(page), before);
      assert.equal(await page.locator('#completion').isVisible(), false);
    }
    await page.locator('#help-confirm').focus();
    const prevented = await page.evaluate(() => ['Enter', ' '].map(key =>
      !document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key, repeat: true, bubbles: true, cancelable: true }))));
    assert.deepEqual(prevented, [true, true]);
    assert.deepEqual(await stored(page), before);
    await page.locator('#help-back').click();
  }
});

test('opening help cancels an unfinished target; old target and help callbacks cannot qualify or fault a new selection', async t => {
  const page = await open(t);
  await enterBoss(page);
  await page.keyboard.type('bike');
  await page.evaluate(() => { window.__oldTarget = window.__speech.active; window.__speech.chineseMode = 'hold'; });
  const before = await stored(page);
  await help(page, 'learn');
  await page.evaluate(() => { window.__oldHelp = window.__speech.active; });
  await page.locator('#help-leave').click();
  await page.evaluate(() => {
    window.__oldTarget.onend(); window.__oldTarget.onerror({ error: 'failed' });
    window.__oldHelp.onend(); window.__oldHelp.onerror({ error: 'not-allowed' });
  });
  assert.equal(await page.locator('#submit').isDisabled(), true);
  assert.equal(await page.locator('#audio-continue').isVisible(), false);
  assert.match(await page.locator('#help-confirm').innerText(), /普通/);
  assert.deepEqual(await stored(page), before);
  await page.locator('#help-back').click();
  await page.waitForFunction(() => window.__speech.active.text === 'bike' && window.__speech.active !== window.__oldTarget && window.__speech.active.__started);
  await page.evaluate(() => { window.__oldHelp.onend(); window.__oldHelp.onerror({ error: 'failed' }); window.__oldTarget.onend(); });
  assert.equal(await page.locator('#submit').isDisabled(), true);
  await hear(page);
  assert.equal(await page.locator('#submit').isEnabled(), true);
  assert.equal(await page.locator('#audio-continue').isVisible(), false);
  assert.deepEqual(await stored(page), before);
});

test('Chinese entry instruction failures still reach English, which alone grants heard qualification', async t => {
  for (const mode of ['language-unavailable', 'voice-unavailable', 'failed', 'not-allowed', 'hold']) {
    const page = await open(t);
    await enterBoss(page, 'recall', mode);
    await page.keyboard.type('bike');
    assert.equal(await page.locator('#submit').isDisabled(), true, mode);
    assert.equal(await page.locator('#audio-continue').isVisible(), false, mode);
    assert.equal((await stored(page)).history.filter(item => item.kind !== 'normal').length, 0);
    await hear(page);
    assert.equal(await page.locator('#submit').isEnabled(), true, mode);
  }
});

test('help explanation failures and blur leave return, change and execution usable without target fault or automatic settlement', async t => {
  for (const mode of ['language-unavailable', 'voice-unavailable', 'failed', 'not-allowed', 'timeout', 'blur']) {
    const page = await open(t);
    await enterBoss(page);
    await page.keyboard.type('bike');
    const before = await stored(page);
    await page.evaluate(mode => { window.__speech.chineseMode = 'hold'; window.__speech.fastTimeout = mode === 'timeout'; }, mode);
    await help(page, 'learn');
    await page.waitForFunction(() => window.__speech.active.lang === 'zh-CN' && window.__speech.active.__started);
    if (mode === 'blur') await page.evaluate(() => window.dispatchEvent(new Event('blur')));
    else if (mode !== 'timeout') await page.evaluate(error => window.__speech.active.onerror({ error }), mode);
    if (mode === 'timeout') await page.waitForFunction(() => document.getElementById('help-notice').textContent.includes('没能播放'));
    assert.equal(await page.locator('#help-back').isEnabled(), true);
    assert.equal(await page.locator('#help-confirm').isEnabled(), true);
    assert.equal(await page.locator('#submit').isDisabled(), true);
    assert.equal(await page.locator('#audio-continue').isVisible(), false);
    assert.deepEqual(await stored(page), before);
    if (mode !== 'blur') {
      assert.equal(await page.locator('#help-notice').isVisible(), true, mode);
      assert.match(await page.locator('#help-notice').innerText(), /声音|语音|说明/);
      assert.equal(await page.locator('#help-learn-retry').isVisible(), true, 'failed explanation offers retry on the same card');
    }
    const count = await page.evaluate(() => window.__speech.items.length);
    await page.locator('#help-learn').click();
    assert.ok(await page.evaluate(() => window.__speech.items.length) > count, 'same card retries explanation');
    await page.locator('#help-leave').click();
    const speechStart = await page.evaluate(() => window.__speech.items.length);
    await page.locator('#help-confirm').click();
    await assertOrdinaryExit(page, before, 'skipped', speechStart);
    await page.evaluate(() => window.__speech.items.slice(0, -1).forEach(item => { item.onend?.(); item.onerror?.({ error: 'failed' }); }));
    assert.equal((await stored(page)).history.length, before.history.length + 1);
    assert.equal(await page.locator('#lesson').evaluate(el => el.classList.contains('boss')), false);
  }
});

test('confirmed learning settles once, reveals only after confirmation and cannot grant rewards through follow-along', async t => {
  const page = await open(t);
  await enterBoss(page);
  const before = await stored(page);
  await help(page, 'learn');
  assert.deepEqual(await page.locator('#slots .slot').allTextContents(), ['·', '·', '·', '·']);
  await page.evaluate(() => { document.getElementById('help-confirm').click(); document.getElementById('help-confirm').click(); });
  assert.deepEqual(await page.locator('#slots .slot').allTextContents(), [...'BIKE']);
  const after = await stored(page);
  assert.equal(after.history.length, before.history.length + 1);
  assert.equal(after.history.at(-1).outcome, 'assisted');
  assert.equal(after.score, before.score);
  assert.equal(after.buffRemaining, 0);
  await page.locator('#practice').click();
  await page.keyboard.type('bike');
  assert.match(await page.locator('#feedback').innerText(), /跟练完成/);
  await page.evaluate(() => { document.getElementById('submit').click(); document.getElementById('help-confirm').click(); });
  assert.deepEqual(await stored(page), after);
});

test('Boss result meaning error or synchronous throw still attempts control instructions and keeps one settlement', async t => {
  const meaning = realWords.find(word => word.id === 'bike-01').meaning;
  for (const outcome of ['assisted', 'correct']) for (const fault of ['error', 'throw']) {
    const page = await open(t);
    await enterBoss(page);
    await hear(page);
    const before = await stored(page);
    await page.evaluate(({ meaning, fault }) => { window.__speech.failText = { [meaning]: fault }; }, { meaning, fault });
    if (outcome === 'assisted') await help(page, 'learn');
    else await page.keyboard.type('bike');
    const speechStart = await page.evaluate(() => window.__speech.items.length);
    await page.locator(outcome === 'assisted' ? '#help-confirm' : '#submit').click();
    await page.waitForFunction(({ start, outcome }) => window.__speech.items.slice(start).some(item =>
      item.lang === 'zh-CN' && (outcome === 'assisted' ? /跟着拼.*普通关/.test(item.text) : /双倍能量.*出发/.test(item.text))),
    { start: speechStart, outcome }, { timeout: 2500 });
    await page.waitForFunction(() => !document.getElementById('next').disabled, null, { timeout: 2500 });
    const spoken = await page.evaluate(start => window.__speech.items.slice(start).map(item => item.text), speechStart);
    assert.ok(spoken.includes('bike'), 'the result attempts the English answer');
    assert.ok(spoken.indexOf('bike') < spoken.indexOf(meaning), 'result English precedes the failed Chinese meaning');
    assert.equal(spoken.filter(text => text === meaning).length, 1, 'only the meaning has an injected failure');
    assert.ok(spoken.slice(spoken.indexOf(meaning) + 1).some(text => /出发|跟着拼/.test(text)), `${outcome}/${fault} attempts the later control explanation`);
    const after = await stored(page);
    assert.equal(after.history.length, before.history.length + 1);
    assert.equal(after.history.at(-1).outcome, outcome);
    assert.equal(after.score, before.score);
    assert.equal(after.buffRemaining, outcome === 'correct' ? 5 : 0);
    assert.equal(await page.locator('#practice').isVisible(), outcome === 'assisted');
    await page.evaluate(() => {
      document.getElementById('submit').click(); document.getElementById('help-confirm').click();
    });
    assert.deepEqual(await stored(page), after);
    await page.locator('#next').click();
    await page.evaluate(meaning => {
      const oldMeaning = window.__speech.items.find(item => item.text === meaning);
      oldMeaning.onend?.(); oldMeaning.onerror?.({ error: 'failed' });
    }, meaning);
    assert.equal(await page.locator('#lesson').evaluate(el => el.classList.contains('boss')), false);
    assert.deepEqual(await stored(page), after, 'continuing and late failed-meaning callbacks cannot settle again');
  }
});

test('leave uses target failure only and goes directly to an ordinary question without revealing Boss answer', async t => {
  for (const mode of ['healthy', 'target-failed', 'heard-then-failed']) {
    const page = await open(t);
    await enterBoss(page, 'image');
    if (mode === 'heard-then-failed') {
      await hear(page);
      await page.evaluate(() => { window.__heardTargetUtterance = window.__speech.active; });
      await page.locator('#listen').click();
      await page.waitForFunction(() => window.__speech.active !== window.__heardTargetUtterance && window.__speech.active.__started);
    }
    if (mode !== 'healthy') await page.evaluate(() => window.__speech.active.onerror({ error: 'failed' }));
    const before = await stored(page);
    const source = mode === 'target-failed' ? '#audio-continue' : '#help';
    await help(page, 'leave', source);
    if (mode === 'target-failed') assert.match(await page.locator('#help-leave').innerText(), /声音/);
    const speechStart = await page.evaluate(() => window.__speech.items.length);
    await page.locator('#help-confirm').click();
    await assertOrdinaryExit(page, before, mode === 'target-failed' ? 'unavailable' : 'skipped', speechStart);
  }
});

test('unfinished help reload and failed-save exit preserve the version 1 storage contract', async t => {
  const page = await open(t);
  await enterBoss(page, 'partial');
  const before = await stored(page);
  const writes = await page.evaluate(() => window.__writes.length);
  await help(page, 'learn');
  assert.equal(await page.evaluate(() => window.__writes.length), writes);
  await page.reload();
  assert.deepEqual(await stored(page), before);
  assert.equal(await page.locator('#help-dialog').isVisible(), false);
  assert.deepEqual(await page.evaluate(() => Object.keys(localStorage).sort()), ['word-adventure-progress-v1']);
  const initial = seed();
  const unsaved = await open(t, { progress: initial, failSave: true });
  await enterBoss(unsaved);
  const count = await unsaved.evaluate(() => window.__writes.length);
  await confirmHelp(unsaved, 'leave');
  assert.equal(await unsaved.locator('#lesson').evaluate(el => el.classList.contains('boss')), false);
  assert.match(await unsaved.locator('#storage-notice').innerText(), /没能保存/);
  assert.deepEqual(await stored(unsaved), initial);
  const pending = await unsaved.evaluate(() => window.__writes);
  assert.equal(pending.length, count + 1);
  const saved = JSON.parse(pending.at(-1).value);
  assert.equal(saved.version, 1);
  assert.deepEqual(Object.keys(saved).sort(), Object.keys(initial).sort());
  assert.equal(saved.history.at(-1).outcome, 'skipped');
  assert.equal(saved.buffRemaining, 0);
});

test('desktop and 390px help controls stay visible, separated and large enough for touch', async t => {
  for (const width of [1080, 390]) {
    const page = await open(t);
    await enterBoss(page);
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await help(page, 'learn');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    const bounds = await page.locator('#help-dialog').boundingBox();
    assert.ok(bounds.x >= 0 && bounds.y >= 0 && bounds.x + bounds.width <= width);
    for (const id of ['help-back', 'help-learn', 'help-leave', 'help-confirm']) {
      const box = await page.locator('#' + id).boundingBox();
      assert.ok(box.width >= 44 && box.height >= 44, `${id} has a touch target`);
      assert.ok(box.x >= 0 && box.x + box.width <= width && box.y >= 0 && box.y + box.height <= (width === 390 ? 844 : 1000), `${id} stays on screen`);
      assert.ok((await page.locator('#' + id).innerText()).trim().length > 0, `${id} retains a readable name for parents`);
    }
    if (process.env.BOSS_SCREENSHOT_DIR) {
      fs.mkdirSync(process.env.BOSS_SCREENSHOT_DIR, { recursive: true });
      await page.screenshot({ path: path.join(process.env.BOSS_SCREENSHOT_DIR, `boss-help-${width === 390 ? 'mobile' : 'desktop'}.png`), fullPage: true });
    }
  }
});
