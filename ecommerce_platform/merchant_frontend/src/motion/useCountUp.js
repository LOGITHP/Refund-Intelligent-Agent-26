import { useState, useEffect } from 'react';
import { usePrefersReducedMotion } from './usePrefersReducedMotion.js';
import { computeCountUpValue } from './math.js';

/**
 * React hook that animates an integer count-up to targetValue using requestAnimationFrame and easeOutCubic.
 * When reduced motion is preferred, immediately settles on targetValue.
 *
 * @param {number} targetValue - Target number to count up to.
 * @param {object} [options]
 * @param {number} [options.durationMs=700] - Total animation duration in milliseconds.
 * @returns {number} The current animated value.
 */
export function useCountUp(targetValue, { durationMs = 700 } = {}) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const safeTarget =
    typeof targetValue === 'number' && Number.isFinite(targetValue) && targetValue > 0
      ? targetValue
      : 0;

  const [value, setValue] = useState(() => (prefersReducedMotion ? safeTarget : 0));

  useEffect(() => {
    if (prefersReducedMotion) {
      setValue(safeTarget);
      return;
    }

    if (durationMs <= 0 || safeTarget === 0) {
      setValue(safeTarget);
      return;
    }

    if (
      typeof window === 'undefined' ||
      typeof window.requestAnimationFrame !== 'function'
    ) {
      setValue(safeTarget);
      return;
    }

    let rafId = null;
    let startTime = null;

    const step = (now) => {
      if (startTime === null) {
        startTime = now;
      }
      const elapsedMs = now - startTime;
      const { value: nextVal, done } = computeCountUpValue({
        target: safeTarget,
        elapsedMs,
        durationMs,
        reducedMotion: false,
      });

      setValue(nextVal);

      if (!done) {
        rafId = window.requestAnimationFrame(step);
      } else {
        rafId = null;
      }
    };

    rafId = window.requestAnimationFrame(step);

    return () => {
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
        rafId = null;
      }
    };
  }, [safeTarget, durationMs, prefersReducedMotion]);

  return value;
}

export default useCountUp;
