import React from 'react';
import {
  Activity,
  ArrowRight,
  Cpu,
  Eye,
  GitBranch,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {
  RevealBox,
  SceneHeader,
  SHIPKART_THEME,
  ShipkartStageBackground,
} from '../components/VideoPrimitives';

export const Scene4SolutionReveal: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Phase 1 fades cleanly out before Phase 2 architectural card rises (zero overlap)
  const phase1Opacity = interpolate(frame, [138, 158], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const phase2Blend = interpolate(frame, [156, 174], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const revealSpring = spring({
    frame: Math.max(0, frame - 160),
    fps,
    config: { damping: 18, stiffness: 120, mass: 0.85 },
  });
  const revealScale = interpolate(revealSpring, [0, 1], [0.96, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const revealY = interpolate(revealSpring, [0, 1], [22, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const barWidth = interpolate(frame, [180, 248], [60, 320], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const pillars = [
    {
      num: '01',
      title: 'Transparent',
      tagline: 'End-to-End Customer Clarity',
      description:
        'Real-time visibility across merchant, gateway, and bank ledgers so customers always know where their money is.',
      icon: Eye,
      accent: SHIPKART_THEME.blue,
      tint: '#eff6ff',
      border: '#bfdbfe',
      delay: 12,
    },
    {
      num: '02',
      title: 'Traceable',
      tagline: 'Verified Ledger & ARN Trail',
      description:
        'Every refund event, payout reference, and settlement handoff is cryptographically and chronologically linked.',
      icon: GitBranch,
      accent: SHIPKART_THEME.green,
      tint: '#f0fdf4',
      border: '#bbf7d0',
      delay: 46,
    },
    {
      num: '03',
      title: 'Intelligent',
      tagline: 'Proactive Agentic Resolution',
      description:
        'AI agents detect stalls early, diagnose root causes, gather evidence, and drive cases toward rapid settlement.',
      icon: Sparkles,
      accent: SHIPKART_THEME.orange,
      tint: '#fff7ed',
      border: '#fed7aa',
      delay: 80,
    },
  ];

  const capabilities = [
    { label: 'Active Lifecycle Monitoring', icon: Activity },
    { label: 'Root-Cause Diagnostics', icon: Cpu },
    { label: 'Human-Governed Escalation', icon: ShieldCheck },
  ];

  return (
    <ShipkartStageBackground
      variant="light"
      sceneTag="PLATFORM VISION"
      sceneIndex={4}
      presenterName="LOGITH P"
    >
      {/* Phase 1 Layer (0..158f): 3 Clean Editorial Pillars */}
      <AbsoluteFill
        style={{
          opacity: phase1Opacity,
          pointerEvents: 'none',
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: 52,
            left: 72,
            right: 72,
            bottom: 170,
            display: 'flex',
            flexDirection: 'column',
            gap: 32,
          }}
        >
          <SceneHeader
            badge="Our Purpose"
            title="Making Every Refund Transparent, Traceable, and Intelligent"
            subtitle="Replacing fragmented status checks with an end-to-end orchestration layer across every financial handoff."
            variant="light"
            delayFrames={0}
          />

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 28,
              flex: 1,
              minHeight: 0,
            }}
          >
            {pillars.map((pillar) => {
              const Icon = pillar.icon;
              return (
                <RevealBox
                  key={pillar.num}
                  delayFrames={pillar.delay}
                  direction="up"
                  distance={34}
                >
                  <div
                    style={{
                      height: '100%',
                      backgroundColor: '#ffffff',
                      borderRadius: 20,
                      border: `1px solid ${SHIPKART_THEME.border}`,
                      boxShadow: '0 8px 24px rgba(15, 35, 58, 0.06)',
                      padding: '34px 32px',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      position: 'relative',
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        right: 0,
                        height: 5,
                        backgroundColor: pillar.accent,
                      }}
                    />

                    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                        }}
                      >
                        <div
                          style={{
                            width: 64,
                            height: 64,
                            borderRadius: 16,
                            backgroundColor: pillar.tint,
                            border: `1px solid ${pillar.border}`,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                          }}
                        >
                          <Icon size={32} color={pillar.accent} />
                        </div>

                        <span
                          className="tabular-nums"
                          style={{
                            fontSize: 42,
                            fontWeight: 900,
                            color: '#e2e8f0',
                            letterSpacing: '-0.04em',
                          }}
                        >
                          {pillar.num}
                        </span>
                      </div>

                      <div>
                        <div
                          style={{
                            fontSize: 12,
                            fontWeight: 800,
                            color: pillar.accent,
                            letterSpacing: '0.08em',
                            textTransform: 'uppercase',
                            marginBottom: 8,
                          }}
                        >
                          {pillar.num} • {pillar.tagline}
                        </div>
                        <h3
                          style={{
                            margin: 0,
                            fontSize: 36,
                            fontWeight: 900,
                            color: SHIPKART_THEME.navy,
                            letterSpacing: '-0.025em',
                          }}
                        >
                          {pillar.title}
                        </h3>
                      </div>

                      <p
                        style={{
                          margin: 0,
                          fontSize: 19,
                          lineHeight: 1.5,
                          color: SHIPKART_THEME.muted,
                          fontWeight: 500,
                        }}
                      >
                        {pillar.description}
                      </p>
                    </div>

                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        paddingTop: 18,
                        borderTop: `1px solid ${SHIPKART_THEME.border}`,
                      }}
                    >
                      <span
                        style={{
                          fontSize: 14,
                          fontWeight: 800,
                          color: SHIPKART_THEME.navy,
                        }}
                      >
                        Core Design Principle
                      </span>
                      <ArrowRight size={18} color={pillar.accent} />
                    </div>
                  </div>
                </RevealBox>
              );
            })}
          </div>
        </div>
      </AbsoluteFill>

      {/* Phase 2 Layer (156..300f): Pure Daylight White Architectural Solution Card */}
      <AbsoluteFill
        style={{
          opacity: phase2Blend,
          pointerEvents: 'none',
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: 56,
            left: 96,
            right: 96,
            bottom: 170,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <div
            style={{
              width: '100%',
              borderRadius: 24,
              backgroundColor: '#ffffff',
              border: `1px solid ${SHIPKART_THEME.border}`,
              borderTop: `6px solid ${SHIPKART_THEME.blue}`,
              boxShadow: '0 16px 42px rgba(15, 35, 58, 0.08)',
              padding: '54px 64px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              textAlign: 'center',
              gap: 24,
              transform: `translateY(${revealY}px) scale(${revealScale})`,
            }}
          >
            {/* Status Pill */}
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 9,
                padding: '7px 18px',
                borderRadius: 9999,
                backgroundColor: '#f0fdf4',
                border: '1px solid #bbf7d0',
                color: SHIPKART_THEME.green,
                fontSize: 13,
                fontWeight: 800,
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
              }}
            >
              <span
                style={{
                  width: 9,
                  height: 9,
                  borderRadius: 9999,
                  backgroundColor: SHIPKART_THEME.green,
                  display: 'inline-block',
                }}
              />
              ACTIVE AI ORCHESTRATION
            </div>

            <div
              style={{
                fontSize: 16,
                fontWeight: 800,
                color: SHIPKART_THEME.blue,
                letterSpacing: '0.14em',
                textTransform: 'uppercase',
              }}
            >
              INTRODUCING OUR SOLUTION
            </div>

            <h1
              style={{
                margin: 0,
                fontSize: 70,
                lineHeight: 1.08,
                fontWeight: 900,
                letterSpacing: '-0.03em',
                color: SHIPKART_THEME.navy,
                maxWidth: 1320,
              }}
            >
              Agentic Refund{' '}
              <span style={{ color: SHIPKART_THEME.blue }}>Intelligence</span> Platform
            </h1>

            {/* Crisp Two-Tone Solid Rule */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div
                style={{
                  height: 5,
                  width: barWidth,
                  borderRadius: 9999,
                  backgroundColor: SHIPKART_THEME.blue,
                }}
              />
              <div
                style={{
                  height: 5,
                  width: 56,
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
                maxWidth: 1060,
              }}
            >
              An intelligent multi-agent layer bridging Shipkart, PayPal, issuing banks,
              and regulatory escalations in real time.
            </p>

            {/* 3 Capability Pills */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 18,
                marginTop: 8,
              }}
            >
              {capabilities.map((cap, i) => {
                const Icon = cap.icon;
                return (
                  <RevealBox
                    key={cap.label}
                    delayFrames={190 + i * 16}
                    direction="up"
                    distance={16}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                        padding: '13px 20px',
                        borderRadius: 14,
                        backgroundColor: '#f8fafc',
                        border: `1px solid ${SHIPKART_THEME.border}`,
                      }}
                    >
                      <Icon size={19} color={SHIPKART_THEME.blue} />
                      <span
                        style={{
                          fontSize: 17,
                          fontWeight: 700,
                          color: SHIPKART_THEME.navy,
                        }}
                      >
                        {cap.label}
                      </span>
                    </div>
                  </RevealBox>
                );
              })}
            </div>
          </div>
        </div>
      </AbsoluteFill>
    </ShipkartStageBackground>
  );
};
