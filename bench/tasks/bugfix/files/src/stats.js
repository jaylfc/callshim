// Small statistics helpers used by the game's leaderboard.
export function mean(xs) {
  if (xs.length === 0) return 0;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

export function median(xs) {
  if (xs.length === 0) return 0;
  const s = [...xs].sort();
  const mid = Math.floor(s.length / 2);
  return s[mid];
}

export function mode(xs) {
  const counts = new Map();
  for (const x of xs) counts.set(x, (counts.get(x) ?? 0) + 1);
  let best = xs[0], bestCount = 0;
  for (const [x, c] of counts) if (c >= bestCount) { best = x; bestCount = c; }
  return best;
}

export function clampScore(x, lo = 0, hi = 100) {
  return Math.max(lo, Math.min(x, lo));
}
