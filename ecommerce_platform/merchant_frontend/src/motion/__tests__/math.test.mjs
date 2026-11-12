import test from 'node:test';
import assert from 'node:assert/strict';
import {
  clamp01,
  lerp,
  easeInOutQuad,
  easeOutCubic,
  computeStaggeredFrame,
  computeCountUpValue,
} from '../math.js';

test('clamp01 clamps values between 0 and 1 and handles non-numeric inputs', () => {
  assert.equal(clamp01(-0.5), 0);
  assert.equal(clamp01(0.42), 0.42);
  assert.equal(clamp01(1.8), 1);
  assert.equal(clamp01(NaN), 0);
  assert.equal(clamp01('invalid'), 0);
  assert.equal(clamp01(null), 0);
});

test('lerp interpolates linearly between start and end', () => {
  assert.equal(lerp(10, 20, 0.25), 12.5);
  assert.equal(lerp(0, 100, 0.5), 50);
  assert.equal(lerp(100, 0, 1), 0);
});

test('easeInOutQuad provides symmetric acceleration and deceleration', () => {
  assert.equal(easeInOutQuad(0), 0);
  assert.equal(easeInOutQuad(0.5), 0.5);
  assert.equal(easeInOutQuad(1), 1);
  assert.ok(easeInOutQuad(0.25) < 0.25, 'should ease in during first half');
  assert.ok(easeInOutQuad(0.75) > 0.75, 'should ease out during second half');
});

test('easeOutCubic provides smooth deceleration', () => {
  assert.equal(easeOutCubic(0), 0);
  assert.equal(easeOutCubic(1), 1);
  assert.equal(easeOutCubic(0.5), 0.875);
  assert.ok(easeOutCubic(0.5) > 0.5, 'easeOutCubic at midpoint is greater than linear 0.5');
});

test('computeCountUpValue interpolates KPI values smoothly from 0 to target', () => {
  const target = 1000;
  const durationMs = 700;

  // At 0ms -> value 0, done false
  const atStart = computeCountUpValue({ target, elapsedMs: 0, durationMs });
  assert.equal(atStart.value, 0);
  assert.equal(atStart.done, false);

  // At halfway -> eased value > linear 0.5 * target
  const atHalf = computeCountUpValue({ target, elapsedMs: 350, durationMs });
  assert.ok(atHalf.value > 0.5 * target, `atHalf.value (${atHalf.value}) should exceed linear (${0.5 * target})`);
  assert.equal(atHalf.value, Math.round(target * 0.875));
  assert.equal(atHalf.done, false);

  // At durationMs -> target, done true
  const atEnd = computeCountUpValue({ target, elapsedMs: 700, durationMs });
  assert.equal(atEnd.value, target);
  assert.equal(atEnd.done, true);

  // Past durationMs -> target, done true
  const pastEnd = computeCountUpValue({ target, elapsedMs: 1200, durationMs });
  assert.equal(pastEnd.value, target);
  assert.equal(pastEnd.done, true);

  // Degenerate duration <= 0 -> target, done true
  const zeroDuration = computeCountUpValue({ target, elapsedMs: 0, durationMs: 0 });
  assert.equal(zeroDuration.value, target);
  assert.equal(zeroDuration.done, true);
});

test('computeCountUpValue clamps negative and non-finite targets to 0', () => {
  const negative = computeCountUpValue({ target: -50, elapsedMs: 350, durationMs: 700 });
  assert.equal(negative.value, 0);
  assert.equal(negative.done, false);

  const nanTarget = computeCountUpValue({ target: NaN, elapsedMs: 350, durationMs: 700 });
  assert.equal(nanTarget.value, 0);
  assert.equal(nanTarget.done, false);

  const undefinedTarget = computeCountUpValue({ target: undefined, elapsedMs: 350, durationMs: 700 });
  assert.equal(undefinedTarget.value, 0);
  assert.equal(undefinedTarget.done, false);

  const nullTarget = computeCountUpValue({ target: null, elapsedMs: 700, durationMs: 700 });
  assert.equal(nullTarget.value, 0);
  assert.equal(nullTarget.done, true);
});

test('computeCountUpValue resolves target immediately when reducedMotion is true', () => {
  const target = 450;
  const reduced = computeCountUpValue({ target, elapsedMs: 0, durationMs: 700, reducedMotion: true });
  assert.deepEqual(reduced, { value: target, done: true });

  const reducedNegative = computeCountUpValue({ target: -10, elapsedMs: 0, durationMs: 700, reducedMotion: true });
  assert.deepEqual(reducedNegative, { value: 0, done: true });
});

test('computeStaggeredFrame delays items sequentially and honors reduced motion', () => {
  // Before start time (index 1 * 70ms = 70ms; elapsed = 40ms)
  const beforeStart = computeStaggeredFrame({
    elapsedMs: 40,
    index: 1,
    delayMs: 70,
    durationMs: 560,
    translateY: 26,
  });
  assert.equal(beforeStart.opacity, 0);
  assert.equal(beforeStart.y, 26);
  assert.equal(beforeStart.done, false);

  // Mid-way through animation
  // index 1 starts at 70ms. At elapsed 350ms, rawT = (350 - 70) / 560 = 280 / 560 = 0.5
  // easeInOutQuad(0.5) = 0.5. opacity = 0.5, y = 13.
  const mid = computeStaggeredFrame({
    elapsedMs: 350,
    index: 1,
    delayMs: 70,
    durationMs: 560,
    translateY: 26,
  });
  assert.equal(mid.opacity, 0.5);
  assert.equal(mid.y, 13);
  assert.equal(mid.done, false);

  // Completed item
  const completed = computeStaggeredFrame({
    elapsedMs: 700,
    index: 1,
    delayMs: 70,
    durationMs: 560,
    translateY: 26,
  });
  assert.deepEqual(completed, { opacity: 1, y: 0, done: true });

  // Reduced motion settles immediately
  const reduced = computeStaggeredFrame({
    elapsedMs: 0,
    index: 3,
    delayMs: 70,
    durationMs: 560,
    translateY: 26,
    reducedMotion: true,
  });
  assert.deepEqual(reduced, { opacity: 1, y: 0, done: true });
});
