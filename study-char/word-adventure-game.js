(function (root, factory) {
  'use strict';
  const api = factory();
  if (root && typeof root === 'object') root.WORD_ADVENTURE_GAME = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function () {
  'use strict';

  const PROGRESS_KEY = 'word-adventure-progress-v1';
  const LEGACY_KEY = 'word-adventure-score-v1';
  const OPTIONS = Object.freeze({
    historyLimit: 100,
    encounterMin: 8,
    encounterMax: 12,
    spellingMin: 3,
    spellingMax: 8,
    buffCount: 5
  });
  const KINDS = new Set(['normal', 'image', 'partial', 'recall']);
  const OUTCOMES = new Set(['correct', 'wrong', 'assisted', 'skipped', 'unavailable']);
  const IMAGE_CONFLICTS = [
    ['🎩', '🧢'],
    ['👦', '🧒']
  ];

  function randomIndex(length, rng) {
    const value = rng();
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value >= 1) {
      throw new Error('rng must return a number in [0, 1)');
    }
    return Math.floor(value * length);
  }

  function wordReward(letterCount) {
    return letterCount <= 3 ? 0.5 : letterCount <= 6 ? 1 : 2;
  }

  function createProgress(legacyScore = 0, rng = Math.random) {
    if (typeof legacyScore !== 'number' || legacyScore < 0 || !Number.isSafeInteger(legacyScore * 2)) {
      throw new Error('legacyScore must be a non-negative safe half-point value');
    }
    return {
      version: 1,
      score: legacyScore,
      buffRemaining: 0,
      untilBoss: OPTIONS.encounterMin + randomIndex(OPTIONS.encounterMax - OPTIONS.encounterMin + 1, rng),
      history: []
    };
  }

  function validHistoryEntry(entry) {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry) ||
        typeof entry.wordId !== 'string' || !entry.wordId.trim() ||
        !KINDS.has(entry.kind) || !OUTCOMES.has(entry.outcome) ||
        !Number.isSafeInteger(entry.endedAt) || entry.endedAt < 0) return null;
    if (entry.kind === 'normal' && entry.outcome !== 'correct') return null;
    if (entry.kind === 'partial') {
      if (!Number.isInteger(entry.missingCount) || entry.missingCount < 1 || entry.missingCount > 4) return null;
      return { wordId: entry.wordId, kind: entry.kind, endedAt: entry.endedAt, outcome: entry.outcome, missingCount: entry.missingCount };
    }
    return { wordId: entry.wordId, kind: entry.kind, endedAt: entry.endedAt, outcome: entry.outcome };
  }

  function parseProgress(raw) {
    let value;
    try {
      if (typeof raw !== 'string') throw new Error('progress must be JSON text');
      value = JSON.parse(raw);
    } catch (_) {
      throw new Error('progress is not valid JSON');
    }
    if (!value || typeof value !== 'object' || Array.isArray(value) || value.version !== 1 ||
        typeof value.score !== 'number' || value.score < 0 || !Number.isSafeInteger(value.score * 2) ||
        !Number.isInteger(value.buffRemaining) || value.buffRemaining < 0 || value.buffRemaining > OPTIONS.buffCount ||
        !Number.isInteger(value.untilBoss) || value.untilBoss < 0 || value.untilBoss > OPTIONS.encounterMax ||
        !Array.isArray(value.history)) {
      throw new Error('progress core fields are invalid or unsupported');
    }
    const history = value.history.map(validHistoryEntry).filter(Boolean).slice(-OPTIONS.historyLimit);
    return { version: 1, score: value.score, buffRemaining: value.buffRemaining, untilBoss: value.untilBoss, history };
  }

  function spellingAllowed(word) {
    if (!word || typeof word.word !== 'string' ||
        !new RegExp(`^[A-Za-z]{${OPTIONS.spellingMin},${OPTIONS.spellingMax}}$`).test(word.word)) return false;
    // Any explicit speech field keeps this entry out of spelling challenges.
    return word.speech === undefined;
  }

  function hasIllustration(word) {
    return !!word && typeof word.illustration === 'string' && word.illustration.length > 0;
  }

  function imagesConflict(left, right) {
    if (left === right) return false;
    return IMAGE_CONFLICTS.some(pair => pair.includes(left) && pair.includes(right));
  }

  function bossCandidates(history, pool) {
    if (!Array.isArray(history) || !Array.isArray(pool)) return [];
    const normalHistory = history.filter(item => item && item.kind === 'normal');
    const recentIds = new Set(normalHistory.slice(-2).map(item => item.wordId));
    const qualifiedIds = new Set(normalHistory.filter(item => item.outcome === 'correct').map(item => item.wordId));
    const byId = new Map();
    for (const word of pool) {
      if (word && typeof word.id === 'string' && !byId.has(word.id)) byId.set(word.id, word);
    }
    const result = [];
    for (const id of qualifiedIds) {
      if (recentIds.has(id)) continue;
      const word = byId.get(id);
      if (!word) continue;
      const kinds = [];
      if (hasIllustration(word) && pool.some(other => other && other.id !== word.id && hasIllustration(other) &&
          other.illustration !== word.illustration && !imagesConflict(word.illustration, other.illustration))) {
        kinds.push('image');
      }
      if (spellingAllowed(word)) kinds.push('partial', 'recall');
      if (kinds.length) result.push({ word, kinds });
    }
    return result;
  }

  function labelForEmoji(emoji, pool) {
    const representative = pool.find(word => hasIllustration(word) && word.illustration === emoji && typeof word.meaning === 'string' && word.meaning.trim());
    return representative ? representative.meaning : emoji;
  }

  function createImageOptions(target, pool, rng) {
    const illustrated = pool.filter(word => hasIllustration(word));
    const distinctSources = illustrated.filter(word => word.id !== target.id && word.illustration !== target.illustration && !imagesConflict(target.illustration, word.illustration));
    if (distinctSources.length === 0) return null;
    const distinct = distinctSources[randomIndex(distinctSources.length, rng)].illustration;
    const thirdSources = illustrated.filter(word => !imagesConflict(target.illustration, word.illustration));
    if (thirdSources.length === 0) return null;
    const third = thirdSources[randomIndex(thirdSources.length, rng)].illustration;
    const emojis = [target.illustration, distinct, third];
    for (let i = emojis.length - 1; i > 0; i--) {
      const j = randomIndex(i + 1, rng);
      [emojis[i], emojis[j]] = [emojis[j], emojis[i]];
    }
    return emojis.map(emoji => ({ emoji, label: labelForEmoji(emoji, pool) }));
  }

  function createBoss(history, pool, rng = Math.random) {
    const candidates = bossCandidates(history, pool);
    if (candidates.length === 0) return null;
    const candidate = candidates[randomIndex(candidates.length, rng)];
    const kinds = candidate.kinds;
    const kind = kinds[randomIndex(kinds.length, rng)];
    const task = { kind, word: candidate.word, missingPositions: [], options: [] };
    if (kind === 'partial') {
      const positions = Array.from({ length: task.word.word.length }, (_, index) => index);
      const missingCount = Math.floor(positions.length / 2);
      for (let i = 0; i < missingCount; i++) {
        const selected = i + randomIndex(positions.length - i, rng);
        [positions[i], positions[selected]] = [positions[selected], positions[i]];
      }
      task.missingPositions = positions.slice(0, missingCount).sort((a, b) => a - b);
    } else if (kind === 'image') {
      task.options = createImageOptions(candidate.word, pool, rng);
      if (!task.options) return null;
    }
    return task;
  }

  function isBossAnswerCorrect(task, input) {
    if (!task || !task.word || typeof task.word.word !== 'string' || typeof input !== 'string') return false;
    if (task.kind === 'image') return input === task.word.illustration;
    if (task.kind === 'partial') {
      if (!Array.isArray(task.missingPositions) || !/^[A-Za-z]+$/.test(input)) return false;
      const expected = task.missingPositions.map(position => task.word.word[position]).join('');
      return input.toUpperCase() === expected.toUpperCase();
    }
    if (task.kind === 'recall') return /^[A-Za-z]+$/.test(input) && input.toUpperCase() === task.word.word.toUpperCase();
    return false;
  }

  function settle(progress, result, rng = Math.random) {
    if (!progress || progress.version !== 1 || !Array.isArray(progress.history) || !result ||
        typeof result.wordId !== 'string' || !result.wordId.trim() || !OUTCOMES.has(result.outcome) ||
        !Number.isSafeInteger(result.endedAt) || result.endedAt < 0 ||
        !KINDS.has(result.kind) || result.kind === 'normal' && result.missingCount !== undefined ||
        result.kind === 'normal' && result.outcome !== 'correct' ||
        result.kind !== 'partial' && result.missingCount !== undefined ||
        result.kind === 'partial' && (!Number.isInteger(result.missingCount) || result.missingCount < 1 || result.missingCount > 4)) {
      throw new Error('settlement input is invalid');
    }
    let reward = 0;
    let buffGranted = false;
    let buffEnded = false;
    const next = {
      version: 1,
      score: progress.score,
      buffRemaining: progress.buffRemaining,
      untilBoss: progress.untilBoss,
      history: progress.history.slice()
    };

    if (result.kind === 'normal') {
      if (result.outcome === 'correct') {
        if (!Number.isInteger(result.letterCount) || result.letterCount < 1) throw new Error('correct normal settlement requires a positive letterCount');
        reward = wordReward(result.letterCount);
        if (progress.buffRemaining > 0) reward *= 2;
      }
      if (progress.buffRemaining > 0) {
        next.buffRemaining = progress.buffRemaining - 1;
        buffEnded = next.buffRemaining === 0;
      } else {
        next.untilBoss = Math.max(0, progress.untilBoss - 1);
      }
    } else {
      next.untilBoss = OPTIONS.encounterMin + randomIndex(OPTIONS.encounterMax - OPTIONS.encounterMin + 1, rng);
      if (result.outcome === 'correct') {
        next.buffRemaining = OPTIONS.buffCount;
        buffGranted = true;
      }
    }

    next.score = progress.score + reward;
    if (!Number.isSafeInteger(next.score * 2)) throw new Error('score overflow');
    const entry = { wordId: result.wordId, kind: result.kind, endedAt: result.endedAt, outcome: result.outcome };
    if (result.kind === 'partial') entry.missingCount = result.missingCount;
    next.history = progress.history.concat(entry).slice(-OPTIONS.historyLimit);
    return { progress: next, reward, buffGranted, buffEnded };
  }

  return Object.freeze({
    PROGRESS_KEY,
    LEGACY_KEY,
    OPTIONS,
    wordReward,
    createProgress,
    parseProgress,
    bossCandidates,
    createBoss,
    isBossAnswerCorrect,
    settle
  });
});
