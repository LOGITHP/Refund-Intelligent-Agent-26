import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { getActiveSubtitleCue } from '../data/narration';

function escapeRegExp(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function renderHighlightedText(
  text: string,
  highlightTerms?: readonly string[],
): React.ReactNode {
  if (!highlightTerms || highlightTerms.length === 0) {
    return text;
  }

  const sortedTerms = [...highlightTerms]
    .filter((term) => term.trim().length > 0)
    .sort((a, b) => b.length - a.length);

  if (sortedTerms.length === 0) {
    return text;
  }

  const pattern = new RegExp(`(${sortedTerms.map(escapeRegExp).join('|')})`, 'gi');
  const parts = text.split(pattern);

  return parts.map((part, index) => {
    const isHighlight = sortedTerms.some(
      (term) => term.toLowerCase() === part.toLowerCase(),
    );
    if (isHighlight) {
      return (
        <span key={index} className="text-[#ffe11b] font-semibold">
          {part}
        </span>
      );
    }
    return <React.Fragment key={index}>{part}</React.Fragment>;
  });
}

export const SubtitleBar: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cue = getActiveSubtitleCue(frame);

  if (!cue) {
    return null;
  }

  const localFrame = Math.max(0, frame - cue.startFrame);

  const enterSpring = spring({
    frame: localFrame,
    fps,
    config: {
      damping: 22,
      stiffness: 240,
      mass: 0.65,
    },
  });

  const slideY = interpolate(enterSpring, [0, 1], [cue.id === 1 && localFrame < 6 ? 0 : 8, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const opacity =
    cue.id === 1 && localFrame < 6
      ? 1
      : interpolate(localFrame, [0, 6], [0.75, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });

  return (
    <div
      className="absolute bottom-8 left-1/2 w-[1560px] pointer-events-none z-50"
      style={{
        transform: `translate(-50%, ${slideY}px)`,
        opacity,
      }}
    >
      <div className="rounded-2xl bg-[#0f233a]/95 border border-white/15 shadow-2xl px-8 py-4 backdrop-blur-md">
        <p className="text-[28px] leading-[1.35] font-medium text-white text-center max-w-[1460px] mx-auto">
          {renderHighlightedText(cue.text, cue.highlightTerms)}
        </p>
      </div>
    </div>
  );
};
