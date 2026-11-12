import { useEffect } from 'react';
import { usePrefersReducedMotion } from './usePrefersReducedMotion.js';
import { computeStaggeredFrame } from './math.js';

/**
 * React hook that cascades entrance animations across child elements with [data-staggered-item].
 *
 * @param {import('react').RefObject<HTMLElement>} containerRef
 * @param {object} [options]
 * @param {any} [options.triggerKey]
 * @param {number} [options.delayMs=70]
 * @param {number} [options.translateY=26]
 * @param {number} [options.durationMs=560]
 * @returns {void}
 */
export function useStaggeredReveal(containerRef, options = {}) {
  const {
    triggerKey,
    delayMs = 70,
    translateY = 26,
    durationMs = 560,
  } = options;

  const prefersReducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    const container = containerRef?.current;
    if (!container) return;

    const items = Array.from(container.querySelectorAll('[data-staggered-item]'));
    if (items.length === 0) return;

    const resetInlineStyles = () => {
      items.forEach((el) => {
        if (el) {
          el.style.opacity = '';
          el.style.transform = '';
        }
      });
    };

    if (prefersReducedMotion) {
      resetInlineStyles();
      return;
    }

    let rafId = null;
    let observer = null;
    let started = false;

    const startAnimation = () => {
      if (started) return;
      started = true;

      let startTime = null;

      const step = (now) => {
        if (!startTime) startTime = now;
        const elapsed = now - startTime;
        let allDone = true;

        items.forEach((el, index) => {
          if (!el) return;

          const frame = computeStaggeredFrame({
            elapsedMs: elapsed,
            index,
            delayMs,
            durationMs,
            translateY,
            reducedMotion: false,
          });

          if (frame.done) {
            el.style.opacity = '';
            el.style.transform = '';
          } else {
            allDone = false;
            el.style.opacity = String(frame.opacity);
            el.style.transform = `matrix(1, 0, 0, 1, 0, ${frame.y})`;
          }
        });

        if (!allDone) {
          rafId = window.requestAnimationFrame(step);
        } else {
          rafId = null;
        }
      };

      rafId = window.requestAnimationFrame(step);
    };

    // Before rAF starts, prepare elements at initial offset
    items.forEach((el) => {
      if (el) {
        el.style.opacity = '0';
        el.style.transform = `matrix(1, 0, 0, 1, 0, ${translateY})`;
      }
    });

    // Check if element is already in viewport or if IntersectionObserver is unavailable
    if (typeof window === 'undefined' || typeof IntersectionObserver === 'undefined') {
      startAnimation();
      return () => {
        if (rafId !== null) {
          window.cancelAnimationFrame(rafId);
          rafId = null;
        }
        resetInlineStyles();
      };
    }

    const rect = container.getBoundingClientRect();
    const isAlreadyInViewport =
      rect.top < window.innerHeight && rect.bottom > 0;

    if (isAlreadyInViewport) {
      startAnimation();
    } else {
      observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              if (observer) {
                observer.disconnect();
                observer = null;
              }
              startAnimation();
              break;
            }
          }
        },
        {
          threshold: 0.08,
          rootMargin: '0px 0px -8% 0px',
        }
      );
      observer.observe(container);
    }

    return () => {
      if (observer) {
        observer.disconnect();
        observer = null;
      }
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
        rafId = null;
      }
      resetInlineStyles();
    };
  }, [containerRef, triggerKey, delayMs, translateY, durationMs, prefersReducedMotion]);
}

export default useStaggeredReveal;
