import { useState, useEffect } from 'react';
import { usePrefersReducedMotion } from './usePrefersReducedMotion.js';
import { computeScrollFraction } from './math.js';

/**
 * React hook tracking scroll progress of a container element relative to the viewport.
 * Returns a normalized progress value between 0.0 and 1.0.
 *
 * @param {import('react').RefObject<HTMLElement>} containerRef
 * @param {object} [options]
 * @param {boolean} [options.reducedMotion]
 * @returns {number}
 */
export function useScrollProgress(containerRef, options = {}) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const reducedMotion = options.reducedMotion ?? prefersReducedMotion;
  const [progress, setProgress] = useState(reducedMotion ? 0.5 : 0);

  useEffect(() => {
    if (reducedMotion) {
      setProgress(0.5);
      return;
    }

    if (typeof window === 'undefined') return;

    let rafId = null;

    const update = () => {
      rafId = null;
      const node = containerRef?.current;
      if (!node) return;

      const rect = node.getBoundingClientRect();
      const next = computeScrollFraction({
        rectTop: rect.top,
        trackHeight: rect.height,
        viewportHeight: window.innerHeight,
        reducedMotion: false,
      });

      setProgress(next);
    };

    const onScrollOrResize = () => {
      if (rafId === null) {
        rafId = window.requestAnimationFrame(update);
      }
    };

    window.addEventListener('scroll', onScrollOrResize, { passive: true });
    window.addEventListener('resize', onScrollOrResize, { passive: true });

    // Initial sync
    update();

    return () => {
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
        rafId = null;
      }
      window.removeEventListener('scroll', onScrollOrResize);
      window.removeEventListener('resize', onScrollOrResize);
    };
  }, [containerRef, reducedMotion]);

  return progress;
}

export default useScrollProgress;
