import test from 'node:test';
import assert from 'node:assert/strict';
import {
  clamp01,
  lerp,
  easeInOutQuad,
  computeScrollFraction,
  computeStaggeredFrame,
} from '../math.js';

test('clamp01 clamps below 0 and above 1', () => {
  assert.equal(clamp01(-0.5), 0);
  assert.equal(clamp01(0.42), 0.42);
  assert.equal(clamp01(1.8), 1);
});

test('lerp and easeInOutQuad interpolate smoothly between endpoints', () => {
  assert.equal(lerp(10, 20, 0.25), 12.5);
  assert.equal(easeInOutQuad(0), 0);
  assert.equal(easeInOutQuad(0.5), 0.5);
  assert.equal(easeInOutQuad(1), 1);
  assert.ok(easeInOutQuad(0.25) < 0.25);
});

test('computeScrollFraction handles track range and degenerate zero-travel tracks safely', () => {
  assert.equal(
    computeScrollFraction({ rectTop: 0, trackHeight: 1600, viewportHeight: 800 }),
    0
  );
  assert.equal(
    computeScrollFraction({ rectTop: -400, trackHeight: 1600, viewportHeight: 800 }),
    0.5
  );
  assert.equal(
    computeScrollFraction({ rectTop: -950, trackHeight: 1600, viewportHeight: 800 }),
    1
  );
  // Mobile / short container guard: trackHeight <= viewportHeight
  assert.equal(
    computeScrollFraction({ rectTop: 100, trackHeight: 500, viewportHeight: 800 }),
    0.5
  );
  // Reduced motion always settles on center frame
  assert.equal(
    computeScrollFraction({ rectTop: -100, trackHeight: 1600, viewportHeight: 800, reducedMotion: true }),
    0.5
  );
});

test('computeStaggeredFrame delays items sequentially and honors reduced motion', () => {
  const beforeStart = computeStaggeredFrame({
    elapsedMs: 40,
    index: 1,
    delayMs: 70,
    durationMs: 500,
    translateY: 26,
  });
  assert.equal(beforeStart.opacity, 0);
  assert.equal(beforeStart.y, 26);
  assert.equal(beforeStart.done, false);

  const mid = computeStaggeredFrame({
    elapsedMs: 320,
    index: 1,
    delayMs: 70,
    durationMs: 500,
    translateY: 26,
  });
  assert.equal(mid.opacity, 0.5);
  assert.equal(mid.y, 13);
  assert.equal(mid.done, false);

  const settled = computeStaggeredFrame({
    elapsedMs: 0,
    index: 3,
    delayMs: 70,
    durationMs: 500,
    translateY: 26,
    reducedMotion: true,
  });
  assert.deepEqual(settled, { opacity: 1, y: 0, done: true });
});
