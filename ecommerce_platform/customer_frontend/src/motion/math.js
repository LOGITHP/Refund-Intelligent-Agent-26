/**
 * Motion math helpers and easing functions for Apple-inspired UI interactions.
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

export function computeScrollFraction({
  rectTop,
  trackHeight,
  viewportHeight,
  reducedMotion = false,
} = {}) {
  if (reducedMotion) return 0.5;

  if (
    typeof rectTop !== 'number' ||
    !Number.isFinite(rectTop) ||
    typeof trackHeight !== 'number' ||
    !Number.isFinite(trackHeight) ||
    typeof viewportHeight !== 'number' ||
    !Number.isFinite(viewportHeight) ||
    viewportHeight <= 0 ||
    trackHeight <= viewportHeight
  ) {
    return 0.5;
  }

  const travel = trackHeight - viewportHeight;
  if (travel <= 0) return 0.5;

  return clamp01(-rectTop / travel);
}

export function computeStaggeredFrame({
  elapsedMs = 0,
  index = 0,
  delayMs = 70,
  durationMs = 500,
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
