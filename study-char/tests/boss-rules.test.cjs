const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const game = require('../word-adventure-game.js');

const fixed = value => () => value;
const word = (id, spelling, illustration = '', extras = {}) => ({
  id,
  word: spelling,
  meaning: `${spelling} meaning`,
  illustration,
  ...extras
});
const normal = (wordId, outcome = 'correct', endedAt = 1) => ({ wordId, kind: 'normal', endedAt, outcome });

test('browser script and CommonJS expose the same API shape and keys', () => {
  const sandbox = { window: {} };
  vm.runInNewContext(fs.readFileSync(require.resolve('../word-adventure-game.js'), 'utf8'), sandbox);
  assert.equal(sandbox.window.WORD_ADVENTURE_GAME.PROGRESS_KEY, game.PROGRESS_KEY);
  assert.equal(game.PROGRESS_KEY, 'word-adventure-progress-v1');
  assert.equal(game.LEGACY_KEY, 'word-adventure-score-v1');
  assert.deepEqual({ ...game.OPTIONS }, {
    historyLimit: 100, encounterMin: 8, encounterMax: 12,
    spellingMin: 3, spellingMax: 8, buffCount: 5
  });
});

test('progress accepts half-point scores and discards malformed history while retaining the newest valid tail', () => {
  const history = Array.from({ length: 104 }, (_, i) => ({
    wordId: `w${i}`, kind: 'normal', endedAt: i, outcome: 'correct'
  }));
  history[2] = { ...history[2], outcome: 'not-a-result' };
  history[3] = { wordId: 'broken', kind: 'partial', endedAt: 3, outcome: 'correct' };
  history[4] = { ...history[4], outcome: 'wrong' };
  const parsed = game.parseProgress(JSON.stringify({
    version: 1, score: 12.5, buffRemaining: 5, untilBoss: 0, history
  }));
  assert.equal(parsed.score, 12.5);
  assert.equal(parsed.history.length, 100);
  assert.equal(parsed.history[0].wordId, 'w1');
  assert.equal(parsed.history.at(-1).wordId, 'w103');
  assert.deepEqual(parsed.history.find(item => item.wordId === 'w3' || item.wordId === 'w4'), undefined);
  assert.deepEqual(game.createProgress(7.5, fixed(0)), {
    version: 1, score: 7.5, buffRemaining: 0, untilBoss: 8, history: []
  });
  assert.equal(game.createProgress(0, fixed(0.999)).untilBoss, 12);
});

test('unsupported or corrupt core progress rejects instead of silently resetting', () => {
  const base = { version: 1, score: 2, buffRemaining: 0, untilBoss: 8, history: [] };
  for (const change of [
    { version: 2 }, { score: -0.5 }, { score: 0.1 }, { score: Number.MAX_SAFE_INTEGER },
    { buffRemaining: 6 }, { buffRemaining: 1.5 }, { untilBoss: 13 }, { untilBoss: -1 }, { history: {} }
  ]) {
    assert.throws(() => game.parseProgress(JSON.stringify({ ...base, ...change })));
  }
  assert.throws(() => game.parseProgress('{'));
  assert.throws(() => game.createProgress(0.1));
});

test('candidate pool deduplicates learned words, excludes the latest two normal words, and falls back to spelling', () => {
  const pool = [
    word('plain', 'ICE CREAM'),
    word('too-short', 'IT'),
    word('phrase', 'ICE CREAM'),
    word('special', 'TV', '', { speech: 'T V' }),
    word('same-speech', 'BIRD', '', { speech: 'BIRD' }),
    word('emoji-only', 'LONGWORD', '🎈'),
    word('distractor', 'BIRD', '🐦')
  ];
  const history = [
    normal('plain', 'correct', 1), normal('plain', 'correct', 2),
    normal('too-short'), normal('phrase'), normal('special'), normal('same-speech'), normal('emoji-only'),
    normal('plain', 'wrong', 7), normal('recent-a', 'wrong', 8), normal('recent-b', 'wrong', 9)
  ];
  const candidates = game.bossCandidates(history, pool);
  assert.equal(candidates.length, 1);
  assert.equal(candidates[0].word.id, 'emoji-only');
  assert.deepEqual(candidates[0].kinds, ['image', 'partial', 'recall']);

  const noImageHistory = [normal('plain'), normal('x'), normal('y')];
  assert.deepEqual(game.bossCandidates(noImageHistory, [word('plain', 'PLAIN')]).map(item => item.kinds), [['partial', 'recall']]);
});

test('sampling is per distinct eligible word and then per that word’s available kinds', () => {
  const pool = [word('a', 'CAT'), word('b', 'FISH'), word('c', 'ELEPHANT')];
  const history = [normal('a'), normal('a'), normal('b'), normal('c'), normal('recent-1'), normal('recent-2')];
  const candidates = game.bossCandidates(history, pool);
  assert.deepEqual(candidates.map(item => item.word.id), ['a', 'b', 'c']);
  // Boundary values choose each distinct candidate in turn; repeats in history do not add slots.
  assert.equal(game.createBoss(history, pool, fixed(0)).word.id, 'a');
  assert.equal(game.createBoss(history, pool, fixed(0.34)).word.id, 'b');
  assert.equal(game.createBoss(history, pool, fixed(0.67)).word.id, 'c');
  // Candidate 'a' has two spelling forms; the second draw is uniform over its own legal kinds.
  assert.equal(game.createBoss(history, pool, (() => { const values = [0, 0.99]; return () => values.shift() ?? 0; })()).kind, 'recall');
});

test('image construction keeps full Unicode, avoids known picture conflicts, and accepts every matching picture', () => {
  const pool = [word('hat', 'HAT', '🎩'), word('cap', 'CAP', '🧢')];
  const history = [normal('hat'), normal('recent-a'), normal('recent-b')];
  const candidates = game.bossCandidates(history, pool);
  assert.equal(candidates[0].kinds.includes('image'), false);

  const bikePool = [
    word('bike', 'BIKE', '🚲'), word('bicycle', 'BICYCLE', '🚲'), word('dog', 'DOG', '🐶'),
    word('family', 'FAMILY', '👨‍👩‍👧‍👦'), word('city', 'CITY', '🏙️')
  ];
  const imageHistory = [normal('bike'), normal('recent-a'), normal('recent-b')];
  const task = game.createBoss(imageHistory, bikePool, fixed(0));
  const forced = { ...task, kind: 'image', options: [
    { emoji: '🚲', label: '自行车' }, { emoji: '🚲', label: '自行车' }, { emoji: '🐶', label: '狗' }
  ] };
  assert.equal(game.isBossAnswerCorrect(forced, '🚲'), true);
  assert.equal(game.isBossAnswerCorrect(forced, '🐶'), false);
  assert.equal(game.isBossAnswerCorrect(forced, '🚲️'), false);
  assert.ok(task.options.some(option => option.emoji === '🚲'));
  assert.ok(task.options.some(option => option.emoji === '👨‍👩‍👧‍👦' || option.emoji === '🏙️' || option.emoji === '🐶'));
  assert.ok(task.options.every(option => typeof option.label === 'string' && option.label.length > 0));

  const unicodePool = [
    word('family', 'FAMILY', '👨‍👩‍👧‍👦'), word('city', 'CITY', '🏙️'), word('cat', 'CAT', '🐱')
  ];
  const unicodeTask = game.createBoss([normal('family'), normal('near-a'), normal('near-b')], unicodePool, fixed(0));
  assert.equal(unicodeTask.kind, 'image');
  assert.ok(unicodeTask.options.some(option => option.emoji === '👨‍👩‍👧‍👦'));
  assert.equal(game.isBossAnswerCorrect(unicodeTask, '👨‍👩‍👧‍👦'), true);
  assert.equal(game.isBossAnswerCorrect(unicodeTask, '👨👩👧👦'), false);
  const variationTask = game.createBoss([normal('city'), normal('near-a'), normal('near-b')], unicodePool, fixed(0));
  assert.ok(variationTask.options.some(option => option.emoji === '🏙️'));
  assert.equal(game.isBossAnswerCorrect(variationTask, '🏙️'), true);
  assert.equal(game.isBossAnswerCorrect(variationTask, '🏙'), false);
});

test('partial challenge uses sorted hidden positions and accepts only the hidden-letter sequence', () => {
  const pool = [word('planet', 'PLANET'), word('cat', 'CAT')];
  const history = [normal('planet'), normal('recent-a'), normal('recent-b')];
  const task = game.createBoss(history, pool, fixed(0));
  assert.equal(task.kind, 'partial');
  assert.equal(task.missingPositions.length, Math.floor(task.word.word.length / 2));
  assert.deepEqual(task.missingPositions, [...new Set(task.missingPositions)].sort((a, b) => a - b));
  const hidden = task.missingPositions.map(index => task.word.word[index]).join('');
  assert.equal(game.isBossAnswerCorrect(task, hidden), true);
  assert.equal(game.isBossAnswerCorrect(task, task.word.word), false);
  assert.equal(game.isBossAnswerCorrect(task, hidden.slice(0, -1)), false);
  assert.equal(game.isBossAnswerCorrect({ ...task, kind: 'recall' }, 'planet'), true);
  assert.equal(game.isBossAnswerCorrect({ ...task, kind: 'recall' }, 'PLANE T'), false);
});

test('same-emoji-only picture pool has no image challenge and falls back to spelling', () => {
  const pool = [word('bike', 'BIKE', '🚲'), word('bicycle', 'BICYCLE', '🚲')];
  const history = [normal('bike'), normal('near-a'), normal('near-b')];
  const candidate = game.bossCandidates(history, pool)[0];
  assert.deepEqual(candidate.kinds, ['partial', 'recall']);
  const task = game.createBoss(history, pool, fixed(0));
  assert.ok(task);
  assert.equal(task.kind, 'partial');
});

test('fifth ordinary completion consumes and earns the final double; sixth gets base reward', () => {
  let progress = { version: 1, score: 10, buffRemaining: 5, untilBoss: 4, history: [] };
  for (let i = 0; i < 5; i++) {
    const result = game.settle(progress, { wordId: `w${i}`, kind: 'normal', outcome: 'correct', endedAt: i, letterCount: 3 }, fixed(0));
    progress = result.progress;
    assert.equal(result.reward, 1);
  }
  assert.equal(progress.score, 15);
  assert.equal(progress.buffRemaining, 0);
  assert.equal(progress.untilBoss, 4);
  const sixth = game.settle(progress, { wordId: 'six', kind: 'normal', outcome: 'correct', endedAt: 6, letterCount: 3 }, fixed(0));
  assert.equal(sixth.reward, 0.5);
  assert.equal(sixth.progress.score, 15.5);
  assert.equal(sixth.progress.untilBoss, 3);
});

test('boss outcomes reset the encounter interval; only success grants five buffs', () => {
  const progress = { version: 1, score: 2, buffRemaining: 0, untilBoss: 0, history: [] };
  const won = game.settle(progress, { wordId: 'cat', kind: 'recall', outcome: 'correct', endedAt: 8 }, fixed(0.5));
  assert.equal(won.progress.buffRemaining, 5);
  assert.equal(won.progress.untilBoss, 10);
  assert.equal(won.buffGranted, true);
  const skipped = game.settle(progress, { wordId: 'cat', kind: 'image', outcome: 'skipped', endedAt: 9 }, fixed(0.99));
  assert.equal(skipped.progress.buffRemaining, 0);
  assert.equal(skipped.progress.untilBoss, 12);
  assert.equal(skipped.progress.score, 2);
});

test('settlement stores only minimal history, trims to 100, and leaves source progress intact on overflow', () => {
  const progress = {
    version: 1, score: 1, buffRemaining: 0, untilBoss: 8,
    history: Array.from({ length: 100 }, (_, i) => normal(`old-${i}`, 'correct', i))
  };
  const result = game.settle(progress, {
    wordId: 'masked', kind: 'partial', outcome: 'wrong', endedAt: 101, missingCount: 2
  }, fixed(0));
  assert.equal(result.progress.history.length, 100);
  assert.equal(result.progress.history[0].wordId, 'old-1');
  assert.deepEqual(result.progress.history.at(-1), {
    wordId: 'masked', kind: 'partial', endedAt: 101, outcome: 'wrong', missingCount: 2
  });
  const overflowBase = { version: 1, score: Number.MAX_SAFE_INTEGER / 2, buffRemaining: 0, untilBoss: 1, history: [] };
  const before = structuredClone(overflowBase);
  assert.throws(() => game.settle(overflowBase, {
    wordId: 'overflow', kind: 'normal', outcome: 'correct', endedAt: 1, letterCount: 7
  }));
  assert.throws(() => game.settle({ version: 1, score: 0, buffRemaining: 0, untilBoss: 8, history: [] }, {
    wordId: 'failed-normal', kind: 'normal', outcome: 'wrong', endedAt: 1
  }));
  assert.throws(() => game.settle({ version: 1, score: 0, buffRemaining: 0, untilBoss: 8, history: [] }, {
    wordId: 'zero-length', kind: 'normal', outcome: 'correct', endedAt: 1, letterCount: 0
  }));
  assert.deepEqual(overflowBase, before);
});
