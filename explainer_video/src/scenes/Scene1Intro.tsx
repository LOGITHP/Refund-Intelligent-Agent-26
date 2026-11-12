import React from 'react';
import { Bot, CreditCard, ShoppingBag } from 'lucide-react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import {
  RevealBox,
  SHIPKART_THEME,
  ShipkartStageBackground,
} from '../components/VideoPrimitives';

export const Scene1Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleSpring = spring({
    frame: Math.max(0, frame - 8),
    fps,
    config: { damping: 20, stiffness: 125, mass: 0.85 },
  });
  const titleOpacity = interpolate(frame, [0, 32], [0.6, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const titleY = interpolate(titleSpring, [0, 1], [16, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // Solid crisp blue underline bar (no gradient)
  const underlineWidth = interpolate(frame, [20, 95], [72, 260], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const chips = [
    {
      label: 'Shipkart Commerce',
      sublabel: 'Customer & Merchant Ledger',
      icon: ShoppingBag,
      accent: SHIPKART_THEME.blue,
      tint: '#eff6ff',
      delay: 48,
    },
    {
      label: 'PayPal Direct Bridge',
      sublabel: 'Merchant-Controlled Settlement',
      icon: CreditCard,
      accent: '#0070ba',
      tint: '#f0f9ff',
      delay: 72,
    },
    {
      label: '3-Agent AI Resolution',
      sublabel: 'Evidence & Human Approval',
      icon: Bot,
      accent: SHIPKART_THEME.green,
      tint: '#f0fdf4',
      delay: 96,
    },
  ];

  return (
    <ShipkartStageBackground
      variant="light"
      sceneTag="PRESENTATION"
      sceneIndex={1}
    >
      {/* Clean centered editorial daylight layout */}
      <div
        style={{
          position: 'absolute',
          top: 56,
          left: 92,
          right: 92,
          bottom: 170,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          gap: 32,
        }}
      >
        {/* Center Hero Card — Architectural Pure White Canvas */}
        <div
          style={{
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
            backgroundColor: '#ffffff',
            borderRadius: 24,
            border: `1px solid ${SHIPKART_THEME.border}`,
            borderTop: `5px solid ${SHIPKART_THEME.blue}`,
            boxShadow: '0 12px 34px rgba(15, 35, 58, 0.06)',
            padding: '52px 56px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-start',
            gap: 22,
          }}
        >
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 16px',
              borderRadius: 8,
              backgroundColor: SHIPKART_THEME.amberBg,
              border: '1px solid #fde047',
              color: SHIPKART_THEME.navy,
              fontSize: 14,
              fontWeight: 800,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
            }}
          >
            Agentic Refund Architecture
          </div>

          <h1
            style={{
              margin: 0,
              fontSize: 72,
              lineHeight: 1.07,
              fontWeight: 900,
              letterSpacing: '-0.03em',
              color: SHIPKART_THEME.navy,
            }}
          >
            Agentic Refund{' '}
            <span style={{ color: SHIPKART_THEME.blue }}>Intelligence</span>
            <br />
            and <span style={{ color: SHIPKART_THEME.blue }}>Resolution</span> Platform
          </h1>

          {/* Solid crisp two-tone bar (zero gradient blur) */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div
              style={{
                height: 5,
                width: underlineWidth,
                borderRadius: 9999,
                backgroundColor: SHIPKART_THEME.blue,
              }}
            />
            <div
              style={{
                height: 5,
                width: 48,
                borderRadius: 9999,
                backgroundColor: SHIPKART_THEME.yellow,
              }}
            />
          </div>

          <p
            style={{
              margin: 0,
              fontSize: 24,
              lineHeight: 1.45,
              color: SHIPKART_THEME.muted,
              fontWeight: 500,
              maxWidth: 1200,
            }}
          >
            Transforming multi-party post-return refunds from opaque waiting periods into
            autonomous, evidence-backed, human-governed resolution.
          </p>
        </div>

        {/* Bottom 3 Crisp Architectural Capability Cards */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 20,
          }}
        >
          {chips.map((chip) => {
            const Icon = chip.icon;
            return (
              <RevealBox
                key={chip.label}
                delayFrames={chip.delay}
                direction="up"
                distance={20}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 16,
                    padding: '16px 22px',
                    borderRadius: 16,
                    backgroundColor: '#ffffff',
                    border: `1px solid ${SHIPKART_THEME.border}`,
                    boxShadow: '0 4px 14px rgba(15, 35, 58, 0.05)',
                  }}
                >
                  <div
                    style={{
                      width: 46,
                      height: 46,
                      borderRadius: 12,
                      backgroundColor: chip.tint,
                      border: `1px solid ${chip.accent}33`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    <Icon size={22} color={chip.accent} />
                  </div>
                  <div>
                    <div
                      style={{
                        color: SHIPKART_THEME.navy,
                        fontSize: 18,
                        fontWeight: 800,
                        letterSpacing: '-0.01em',
                      }}
                    >
                      {chip.label}
                    </div>
                    <div
                      style={{
                        color: SHIPKART_THEME.muted,
                        fontSize: 13,
                        fontWeight: 600,
                        marginTop: 2,
                      }}
                    >
                      {chip.sublabel}
                    </div>
                  </div>
                </div>
              </RevealBox>
            );
          })}
        </div>
      </div>
    </ShipkartStageBackground>
  );
};
