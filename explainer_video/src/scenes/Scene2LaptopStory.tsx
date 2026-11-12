import React from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  HelpCircle,
  Laptop,
  PackageCheck,
  SearchX,
  Truck,
} from 'lucide-react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import {
  ImageFrame,
  RevealBox,
  SceneHeader,
  SHIPKART_THEME,
  ShipkartStageBackground,
} from '../components/VideoPrimitives';

export const Scene2LaptopStory: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Timeline progress bars (frames 65..175)
  const step1Progress = interpolate(frame, [65, 110], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const step2Progress = interpolate(frame, [115, 165], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // Pulsing stall ring for Day 14+ STUCK (driven purely by useCurrentFrame)
  const stallPulse = 1 + Math.sin(frame * 0.16) * 0.06;
  const stallGlow = 0.25 + (Math.sin(frame * 0.16) + 1) * 0.15;

  // Pain-point highlight synchronization (local 250..570)
  const painHighlight = spring({
    frame: Math.max(0, frame - 250),
    fps,
    config: { damping: 18, stiffness: 120, mass: 0.8 },
  });
  const cue6ActiveScale = interpolate(painHighlight, [0, 1], [0.98, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const timelineSteps = [
    {
      title: 'Product Returned',
      day: 'Day 1',
      status: 'CONFIRMED',
      detail: 'Return pickup requested on Shipkart app & verified.',
      icon: PackageCheck,
      state: 'done' as const,
      delay: 45,
    },
    {
      title: 'Warehouse Pickup',
      day: 'Day 3',
      status: 'VERIFIED',
      detail: 'ProBook 15" Laptop inspected and accepted at hub.',
      icon: Truck,
      state: 'done' as const,
      delay: 95,
    },
    {
      title: 'Refund Credited ???',
      day: 'Day 14+ STUCK',
      status: 'BLOCKED',
      detail: 'Money left merchant flow — no bank credit or ARN trace.',
      icon: AlertTriangle,
      state: 'stuck' as const,
      delay: 145,
    },
  ];

  const painPoints = [
    {
      title: 'Delays',
      subtitle: '14+ Days Elapsed',
      description: 'Standard 5-day promise broken with silent processing queues.',
      icon: Clock,
      color: SHIPKART_THEME.amber,
      bg: '#fffbeb',
      border: '#fde68a',
      delay: 225,
    },
    {
      title: 'Uncertainty',
      subtitle: 'No Root Cause',
      description: 'Repeated support tickets yield generic "please wait" scripts.',
      icon: HelpCircle,
      color: SHIPKART_THEME.orange,
      bg: '#fff7ed',
      border: '#fed7aa',
      delay: 265,
    },
    {
      title: 'Zero ETA Visibility',
      subtitle: '"Where is my money?"',
      description: 'No live handoff owner, no ARN proof, and no real credit date.',
      icon: SearchX,
      color: SHIPKART_THEME.red,
      bg: '#fef2f2',
      border: '#fecaca',
      delay: 305,
    },
  ];

  return (
    <ShipkartStageBackground
      variant="light"
      sceneTag="REAL-WORLD PROBLEM"
      sceneIndex={2}
      presenterName="LOGITH P"
    >
      {/* Safe content area: y = 52..910 */}
      <div
        style={{
          position: 'absolute',
          top: 52,
          left: 72,
          right: 72,
          bottom: 170,
          display: 'flex',
          flexDirection: 'column',
          gap: 24,
        }}
      >
        <SceneHeader
          badge="Real-World Experience"
          title="Returning a Laptop Was Easy. Getting the Refund Wasn't."
          subtitle="A real online laptop return revealed how broken post-return refund visibility is for everyday customers."
          variant="light"
          delayFrames={0}
        />

        {/* Two-column body */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '0.92fr 1.08fr',
            gap: 28,
            flex: 1,
            minHeight: 0,
          }}
        >
          {/* LEFT COLUMN (0..220f): Laptop Illustration + Shipkart Order Card */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 18,
            }}
          >
            <ImageFrame
              imagePath="images/laptop_refund_story.jpg"
              alt="Returned laptop next to ticking hourglass representing refund delay"
              badge="CASE #LAP-4092"
              caption="Valid Return Completed — Refund Still Pending"
              delayFrames={15}
              zoomDurationFrames={540}
              height={390}
            />

            {/* Realistic Shipkart Order Card */}
            <RevealBox delayFrames={90} direction="up" distance={24}>
              <div
                style={{
                  backgroundColor: '#ffffff',
                  borderRadius: 18,
                  border: `1px solid ${SHIPKART_THEME.border}`,
                  boxShadow: '0 12px 30px rgba(15, 35, 58, 0.08)',
                  padding: '20px 24px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 14,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    borderBottom: `1px solid ${SHIPKART_THEME.border}`,
                    paddingBottom: 12,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <div
                      style={{
                        width: 44,
                        height: 44,
                        borderRadius: 12,
                        backgroundColor: 'rgba(40, 116, 240, 0.1)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <Laptop size={24} color={SHIPKART_THEME.blue} />
                    </div>
                    <div>
                      <div
                        style={{
                          fontSize: 13,
                          fontWeight: 800,
                          color: SHIPKART_THEME.blue,
                          letterSpacing: '0.06em',
                          textTransform: 'uppercase',
                        }}
                      >
                        Shipkart Order #LAP-4092
                      </div>
                      <div
                        style={{
                          fontSize: 21,
                          fontWeight: 800,
                          color: SHIPKART_THEME.navy,
                        }}
                      >
                        ProBook 15" Laptop
                      </div>
                    </div>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div
                      style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: SHIPKART_THEME.muted,
                        textTransform: 'uppercase',
                      }}
                    >
                      Refund Value
                    </div>
                    <div
                      className="tabular-nums"
                      style={{
                        fontSize: 24,
                        fontWeight: 900,
                        color: SHIPKART_THEME.navy,
                      }}
                    >
                      ₹84,990
                    </div>
                  </div>
                </div>

                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span
                      style={{
                        padding: '5px 12px',
                        borderRadius: 9999,
                        backgroundColor: '#dcfce7',
                        color: SHIPKART_THEME.green,
                        fontSize: 13,
                        fontWeight: 800,
                      }}
                    >
                      Return Approved ✓
                    </span>
                    <span
                      style={{
                        padding: '5px 12px',
                        borderRadius: 9999,
                        backgroundColor: '#fef2f2',
                        color: SHIPKART_THEME.red,
                        fontSize: 13,
                        fontWeight: 800,
                      }}
                    >
                      Credit Status: Unresolved (Day 14+)
                    </span>
                  </div>

                  <span
                    style={{
                      fontSize: 14,
                      fontWeight: 700,
                      color: SHIPKART_THEME.muted,
                    }}
                  >
                    ETA: Unknown
                  </span>
                </div>
              </div>
            </RevealBox>
          </div>

          {/* RIGHT COLUMN (180..570f): Visual Contrast Timeline + 3 Pain-Point Cards */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 18,
              justifyContent: 'space-between',
            }}
          >
            {/* Visual Contrast Timeline Card */}
            <RevealBox delayFrames={170} direction="left" distance={30}>
              <div
                style={{
                  backgroundColor: '#ffffff',
                  borderRadius: 20,
                  border: `1px solid ${SHIPKART_THEME.border}`,
                  boxShadow: '0 14px 32px rgba(15, 35, 58, 0.08)',
                  padding: '22px 26px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 16,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <span
                    style={{
                      fontSize: 15,
                      fontWeight: 800,
                      color: SHIPKART_THEME.navy,
                      letterSpacing: '0.04em',
                      textTransform: 'uppercase',
                    }}
                  >
                    Refund Contrast Timeline
                  </span>
                  <span
                    style={{
                      padding: '4px 12px',
                      borderRadius: 9999,
                      backgroundColor: '#fef2f2',
                      border: '1px solid #fecaca',
                      color: SHIPKART_THEME.red,
                      fontSize: 13,
                      fontWeight: 800,
                    }}
                  >
                    STALLED AT SETTLEMENT
                  </span>
                </div>

                {/* 3 Timeline Milestones */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {timelineSteps.map((step, idx) => {
                    const isStuck = step.state === 'stuck';
                    const Icon = step.icon;
                    const barFill = idx === 0 ? step1Progress : idx === 1 ? step2Progress : 0;

                    return (
                      <RevealBox
                        key={step.title}
                        delayFrames={step.delay}
                        direction="left"
                        distance={24}
                      >
                        <div style={{ position: 'relative' }}>
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              padding: '14px 18px',
                              borderRadius: 14,
                              backgroundColor: isStuck ? '#fef2f2' : '#f8fafc',
                              border: isStuck
                                ? `1.5px solid ${SHIPKART_THEME.red}`
                                : `1px solid ${SHIPKART_THEME.border}`,
                              boxShadow: isStuck
                                ? `0 0 24px rgba(220, 38, 38, ${stallGlow})`
                                : 'none',
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                              <div
                                style={{
                                  width: 42,
                                  height: 42,
                                  borderRadius: 12,
                                  backgroundColor: isStuck
                                    ? SHIPKART_THEME.red
                                    : SHIPKART_THEME.green,
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  transform: isStuck ? `scale(${stallPulse})` : 'none',
                                }}
                              >
                                {isStuck ? (
                                  <Icon size={22} color="#ffffff" />
                                ) : (
                                  <CheckCircle2 size={22} color="#ffffff" />
                                )}
                              </div>

                              <div>
                                <div
                                  style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 10,
                                  }}
                                >
                                  <span
                                    style={{
                                      fontSize: 19,
                                      fontWeight: 800,
                                      color: isStuck
                                        ? SHIPKART_THEME.red
                                        : SHIPKART_THEME.navy,
                                    }}
                                  >
                                    {step.title} {isStuck ? '' : '✓'}
                                  </span>
                                  <span
                                    className="tabular-nums"
                                    style={{
                                      padding: '3px 10px',
                                      borderRadius: 9999,
                                      backgroundColor: isStuck
                                        ? '#fee2e2'
                                        : '#dcfce7',
                                      color: isStuck
                                        ? SHIPKART_THEME.red
                                        : SHIPKART_THEME.green,
                                      fontSize: 13,
                                      fontWeight: 800,
                                    }}
                                  >
                                    {step.day}
                                  </span>
                                </div>
                                <div
                                  style={{
                                    fontSize: 14,
                                    color: SHIPKART_THEME.muted,
                                    fontWeight: 500,
                                    marginTop: 2,
                                  }}
                                >
                                  {step.detail}
                                </div>
                              </div>
                            </div>

                            <span
                              style={{
                                fontSize: 12,
                                fontWeight: 800,
                                letterSpacing: '0.06em',
                                color: isStuck
                                  ? SHIPKART_THEME.red
                                  : SHIPKART_THEME.green,
                              }}
                            >
                              {step.status}
                            </span>
                          </div>

                          {/* Connector fill indicator between milestones */}
                          {idx < 2 ? (
                            <div
                              style={{
                                marginLeft: 38,
                                width: 4,
                                height: 14,
                                backgroundColor: '#e2e8f0',
                                overflow: 'hidden',
                              }}
                            >
                              <div
                                style={{
                                  width: '100%',
                                  height: `${barFill * 100}%`,
                                  backgroundColor:
                                    idx === 0
                                      ? SHIPKART_THEME.green
                                      : SHIPKART_THEME.red,
                                }}
                              />
                            </div>
                          ) : null}
                        </div>
                      </RevealBox>
                    );
                  })}
                </div>
              </div>
            </RevealBox>

            {/* 3 Pain-Point Cards synced to Cue 6 (405..570f) */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: 14,
                transform: `scale(${cue6ActiveScale})`,
              }}
            >
              {painPoints.map((pain) => {
                const Icon = pain.icon;
                return (
                  <RevealBox
                    key={pain.title}
                    delayFrames={pain.delay}
                    direction="up"
                    distance={26}
                  >
                    <div
                      style={{
                        height: '100%',
                        backgroundColor: pain.bg,
                        border: `1.5px solid ${pain.border}`,
                        borderRadius: 18,
                        padding: '18px 18px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 10,
                        boxShadow: '0 10px 24px rgba(15, 35, 58, 0.06)',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                        }}
                      >
                        <div
                          style={{
                            width: 40,
                            height: 40,
                            borderRadius: 12,
                            backgroundColor: '#ffffff',
                            border: `1px solid ${pain.border}`,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                          }}
                        >
                          <Icon size={22} color={pain.color} />
                        </div>
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 800,
                            color: pain.color,
                            letterSpacing: '0.06em',
                            textTransform: 'uppercase',
                          }}
                        >
                          PAIN POINT
                        </span>
                      </div>

                      <div>
                        <div
                          style={{
                            fontSize: 21,
                            fontWeight: 900,
                            color: SHIPKART_THEME.navy,
                            lineHeight: 1.15,
                          }}
                        >
                          {pain.title}
                        </div>
                        <div
                          style={{
                            fontSize: 14,
                            fontWeight: 800,
                            color: pain.color,
                            marginTop: 3,
                          }}
                        >
                          {pain.subtitle}
                        </div>
                      </div>

                      <p
                        style={{
                          margin: 0,
                          fontSize: 14,
                          lineHeight: 1.4,
                          color: SHIPKART_THEME.muted,
                          fontWeight: 500,
                        }}
                      >
                        {pain.description}
                      </p>
                    </div>
                  </RevealBox>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </ShipkartStageBackground>
  );
};
