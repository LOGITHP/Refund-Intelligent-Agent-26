/**
 * Motion math helpers, interpolation, and easing curves for Apple-inspired merchant interactions.
 */

export function clamp01(v) {
  if (typeof v !== 'number' || Number.isNaN(v)) return 0;
  return Math.min(Math.max(v, 0), 1);
}

export function lerp(start, end, t) {
  return start + (end - start) * t;
}

export function easeInOutQuad(t) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

export function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

/**
 * Computes an eased numeric value for dashboard KPI count-up animations.
 *
 * @param {object} params
 * @param {number} [params.target=0] - The numeric target value (clamped to >= 0).
 * @param {number} [params.elapsedMs=0] - Time elapsed since animation started.
 * @param {number} [params.durationMs=700] - Total animation duration in milliseconds.
 * @param {boolean} [params.reducedMotion=false] - Whether reduced motion is active.
 * @returns {{ value: number, done: boolean }}
 */
export function computeCountUpValue({
  target = 0,
  elapsedMs = 0,
  durationMs = 700,
  reducedMotion = false,
} = {}) {
  const safeTarget =
    typeof target === 'number' && Number.isFinite(target) && target > 0 ? target : 0;

  if (reducedMotion) {
    return { value: safeTarget, done: true };
  }

  if (durationMs <= 0 || elapsedMs >= durationMs) {
    return { value: safeTarget, done: true };
  }

  if (elapsedMs <= 0) {
    return { value: 0, done: false };
  }

  const rawT = elapsedMs / durationMs;
  const t = clamp01(rawT);
  const eased = easeOutCubic(t);
  const value = Math.round(safeTarget * eased);

  return { value, done: false };
}

/**
 * Computes the staggered opacity and vertical translation frame for a sequence item.
 *
 * @param {object} params
 * @param {number} [params.elapsedMs=0] - Time elapsed since stagger sequence began.
 * @param {number} [params.index=0] - Item index in the sequence.
 * @param {number} [params.delayMs=70] - Delay per item in milliseconds.
 * @param {number} [params.durationMs=560] - Duration per item entrance in milliseconds.
 * @param {number} [params.translateY=26] - Initial vertical offset in pixels.
 * @param {boolean} [params.reducedMotion=false] - Whether reduced motion is active.
 * @returns {{ opacity: number, y: number, done: boolean }}
 */
export function computeStaggeredFrame({
  elapsedMs = 0,
  index = 0,
  delayMs = 70,
  durationMs = 560,
  translateY = 26,
  reducedMotion = false,
} = {}) {
  if (reducedMotion) {
    return { opacity: 1, y: 0, done: true };
  }

  const startTime = index * delayMs;
  if (elapsedMs < startTime) {
    return { opacity: 0, y: translateY, done: false };
  }

  if (durationMs <= 0) {
    return { opacity: 1, y: 0, done: true };
  }

  const rawT = (elapsedMs - startTime) / durationMs;
  if (rawT >= 1) {
    return { opacity: 1, y: 0, done: true };
  }

  const t = easeInOutQuad(clamp01(rawT));
  const opacity = lerp(0, 1, t);
  const y = lerp(translateY, 0, t);

  return { opacity, y, done: false };
}
