import React from 'react';
import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

export const SHIPKART_THEME = {
  navy: '#0f233a',
  navyHover: '#1c3553',
  blue: '#2874f0',
  blueHover: '#1d5ec9',
  blueTint: '#eff6ff',
  yellow: '#ffe11b',
  amberBg: '#fef9c3',
  orange: '#fb641b',
  bg: '#f8fafc',
  surface: '#f4f6f9',
  card: '#ffffff',
  border: '#e2e8f0',
  text: '#0f172a',
  muted: '#475569',
  green: '#16a34a',
  amber: '#d97706',
  red: '#dc2626',
} as const;

export type StageVariant = 'navy' | 'light';

export interface ShipkartStageBackgroundProps {
  variant?: StageVariant;
  sceneTag?: string;
  sceneIndex?: number;
  presenterName?: string;
  children?: React.ReactNode;
}

export const ShipkartStageBackground: React.FC<ShipkartStageBackgroundProps> = ({
  children,
}) => {
  return (
    <AbsoluteFill
      style={{
        width: 1920,
        height: 1080,
        backgroundColor: SHIPKART_THEME.bg,
        overflow: 'hidden',
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
      }}
    >
      {/* Main Content Layer (clean headerless stage) */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          height: '100%',
          zIndex: 10,
        }}
      >
        {children}
      </div>
    </AbsoluteFill>
  );
};

export interface SceneHeaderProps {
  badge: string;
  title: string;
  subtitle?: string;
  variant?: StageVariant;
  delayFrames?: number;
  align?: 'left' | 'center';
  accentColor?: string;
}

export const SceneHeader: React.FC<SceneHeaderProps> = ({
  badge,
  title,
  subtitle,
  delayFrames = 0,
  align = 'left',
  accentColor,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = Math.max(0, frame - delayFrames);
  const progress = spring({
    frame: localFrame,
    fps,
    config: { damping: 18, stiffness: 130, mass: 0.8 },
  });

  const opacity =
    frame < delayFrames
      ? 0
      : interpolate(progress, [0, 1], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
  const translateY = interpolate(progress, [0, 1], [18, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const resolvedAccent = accentColor ?? SHIPKART_THEME.blue;

  return (
    <div
      style={{
        opacity,
        transform: `translateY(${translateY}px)`,
        display: 'flex',
        flexDirection: 'column',
        alignItems: align === 'center' ? 'center' : 'flex-start',
        textAlign: align,
        gap: 10,
      }}
    >
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 8,
          padding: '5px 14px',
          borderRadius: 9999,
          backgroundColor: SHIPKART_THEME.blueTint,
          border: '1px solid #bfdbfe',
          color: SHIPKART_THEME.blue,
          fontSize: 12,
          fontWeight: 800,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
        }}
      >
        <span
          style={{
            width: 7,
            height: 7,
            borderRadius: 9999,
            backgroundColor: resolvedAccent,
            display: 'inline-block',
          }}
        />
        <span>{badge}</span>
      </div>

      <h2
        style={{
          margin: 0,
          fontSize: 44,
          lineHeight: 1.12,
          fontWeight: 800,
          letterSpacing: '-0.025em',
          color: SHIPKART_THEME.navy,
        }}
      >
        {title}
      </h2>

      {subtitle ? (
        <p
          style={{
            margin: 0,
            fontSize: 20,
            lineHeight: 1.4,
            fontWeight: 500,
            color: SHIPKART_THEME.muted,
            maxWidth: align === 'center' ? 920 : 1080,
          }}
        >
          {subtitle}
        </p>
      ) : null}
    </div>
  );
};

export interface RevealBoxProps {
  children: React.ReactNode;
  delayFrames?: number;
  direction?: 'up' | 'left' | 'right' | 'scale';
  distance?: number;
  className?: string;
  style?: React.CSSProperties;
}

export const RevealBox: React.FC<RevealBoxProps> = ({
  children,
  delayFrames = 0,
  direction = 'up',
  distance = 28,
  className = '',
  style = {},
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = Math.max(0, frame - delayFrames);
  const progress = spring({
    frame: localFrame,
    fps,
    config: { damping: 18, stiffness: 120, mass: 0.85 },
  });

  const opacity =
    frame < delayFrames
      ? 0
      : interpolate(progress, [0, 1], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });

  let transform = 'none';
  if (direction === 'up') {
    const ty = interpolate(progress, [0, 1], [distance, 0], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });
    transform = `translateY(${ty}px)`;
  } else if (direction === 'left') {
    const tx = interpolate(progress, [0, 1], [distance, 0], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });
    transform = `translateX(${tx}px)`;
  } else if (direction === 'right') {
    const tx = interpolate(progress, [0, 1], [-distance, 0], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });
    transform = `translateX(${tx}px)`;
  } else if (direction === 'scale') {
    const sc = interpolate(progress, [0, 1], [0.92, 1], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });
    transform = `scale(${sc})`;
  }

  return (
    <div
      className={className}
      style={{
        opacity,
        transform,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

export interface ImageFrameProps {
  imagePath: string;
  alt?: string;
  badge?: string;
  caption?: string;
  delayFrames?: number;
  zoomDurationFrames?: number;
  className?: string;
  style?: React.CSSProperties;
  height?: number;
}

export const ImageFrame: React.FC<ImageFrameProps> = ({
  imagePath,
  alt = 'Illustration',
  badge,
  caption,
  delayFrames = 0,
  zoomDurationFrames = 420,
  className = '',
  style = {},
  height = 380,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = Math.max(0, frame - delayFrames);
  const entrance = spring({
    frame: localFrame,
    fps,
    config: { damping: 18, stiffness: 115, mass: 0.9 },
  });

  const opacity =
    frame < delayFrames
      ? 0
      : interpolate(entrance, [0, 1], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
  const translateY = interpolate(entrance, [0, 1], [20, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const zoom = interpolate(
    frame,
    [delayFrames, delayFrames + zoomDurationFrames],
    [1.0, 1.035],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    }
  );

  const imageHeight = caption || badge ? height - 48 : height;

  return (
    <div
      className={className}
      style={{
        opacity,
        transform: `translateY(${translateY}px)`,
        borderRadius: 18,
        backgroundColor: '#ffffff',
        border: `1px solid ${SHIPKART_THEME.border}`,
        boxShadow: '0 8px 24px rgba(15, 35, 58, 0.06)',
        overflow: 'hidden',
        position: 'relative',
        ...style,
      }}
    >
      <div
        style={{
          width: '100%',
          height: imageHeight,
          overflow: 'hidden',
          position: 'relative',
          backgroundColor: '#f1f5f9',
        }}
      >
        <Img
          src={staticFile(imagePath)}
          alt={alt}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            transform: `scale(${zoom})`,
            transformOrigin: 'center center',
            display: 'block',
          }}
        />
      </div>

      {/* Clean crisp white editorial footer bar (no dark gradient overlay!) */}
      {(badge || caption) ? (
        <div
          style={{
            height: 48,
            backgroundColor: '#ffffff',
            borderTop: `1px solid ${SHIPKART_THEME.border}`,
            paddingLeft: 18,
            paddingRight: 18,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          {caption ? (
            <span
              style={{
                color: SHIPKART_THEME.navy,
                fontSize: 14,
                fontWeight: 700,
                letterSpacing: '-0.01em',
              }}
            >
              {caption}
            </span>
          ) : (
            <span />
          )}

          {badge ? (
            <span
              style={{
                padding: '3px 10px',
                borderRadius: 9999,
                backgroundColor: SHIPKART_THEME.blueTint,
                border: '1px solid #bfdbfe',
                color: SHIPKART_THEME.blue,
                fontSize: 11,
                fontWeight: 800,
                letterSpacing: '0.07em',
                textTransform: 'uppercase',
                flexShrink: 0,
              }}
            >
              {badge}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};
