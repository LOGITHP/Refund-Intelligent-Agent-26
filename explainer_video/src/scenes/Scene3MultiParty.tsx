import React from 'react';
import {
  AlertOctagon,
  Building2,
  CreditCard,
  Landmark,
  Scale,
  Store,
  User,
} from 'lucide-react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import {
  ImageFrame,
  RevealBox,
  SHIPKART_THEME,
  ShipkartStageBackground,
} from '../components/VideoPrimitives';

export const Scene3MultiParty: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 0..165f: Featured Question Banner Entrance
  const bannerSpring = spring({
    frame,
    fps,
    config: { damping: 18, stiffness: 120, mass: 0.85 },
  });
  const bannerOpacity = interpolate(bannerSpring, [0, 1], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const bannerY = interpolate(bannerSpring, [0, 1], [24, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // Pulsing stall beacons (frames 180..540 intensify, driven purely by frame)
  const stallReveal = interpolate(frame, [175, 225], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const pulseWave = (Math.sin(frame * 0.18) + 1) * 0.5;
  const beaconScale = 1 + pulseWave * 0.08;
  const beaconOpacity = (0.72 + pulseWave * 0.28) * stallReveal;

  const parties = [
    {
      step: '1',
      title: 'Customer',
      role: 'Initiates valid return & awaits funds',
      icon: User,
      accent: SHIPKART_THEME.blue,
      delay: 75,
      gapAfter: {
        label: 'Customer Update Gap',
        severity: 'amber' as const,
      },
    },
    {
      step: '2',
      title: 'Merchant (Shipkart)',
      role: 'Validates inspection & triggers refund request',
      icon: Store,
      accent: SHIPKART_THEME.navy,
      delay: 105,
      gapAfter: {
        label: 'Webhook & Queue Handoff',
        severity: 'amber' as const,
      },
    },
    {
      step: '3',
      title: 'Payment Gateway (PayPal)',
      role: 'Processes payout instruction & issues ARN',
      icon: CreditCard,
      accent: '#0070ba',
      delay: 135,
      gapAfter: {
        label: 'Settlement Lag',
        severity: 'red' as const,
      },
    },
    {
      step: '4',
      title: 'Issuing Bank',
      role: 'Clears interbank settlement to customer account',
      icon: Landmark,
      accent: SHIPKART_THEME.amber,
      delay: 165,
      gapAfter: {
        label: 'ARN Blind Spot',
        severity: 'red' as const,
      },
    },
    {
      step: '5',
      title: 'Regulatory Authority',
      role: 'RBI / Ombudsman / Compliance escalation path',
      icon: Scale,
      accent: SHIPKART_THEME.red,
      delay: 195,
      gapAfter: null,
    },
  ];

  return (
    <ShipkartStageBackground
      variant="light"
      sceneTag="ECOSYSTEM GAP"
      sceneIndex={3}
      presenterName="LOGITH P"
    >
      {/* Safe content area: y = 48..910 */}
      <div
        style={{
          position: 'absolute',
          top: 48,
          left: 72,
          right: 72,
          bottom: 170,
          display: 'flex',
          flexDirection: 'column',
          gap: 20,
        }}
      >
        {/* 0..165f: Clean Editorial Question Banner (crisp white + royal blue left rule) */}
        <div
          style={{
            opacity: bannerOpacity,
            transform: `translateY(${bannerY}px)`,
            borderRadius: 18,
            backgroundColor: '#ffffff',
            border: `1px solid ${SHIPKART_THEME.border}`,
            borderLeft: `7px solid ${SHIPKART_THEME.blue}`,
            boxShadow: '0 6px 20px rgba(15, 35, 58, 0.06)',
            padding: '20px 30px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 28,
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span
                style={{
                  padding: '4px 12px',
                  borderRadius: 9999,
                  backgroundColor: SHIPKART_THEME.blue,
                  color: '#ffffff',
                  fontSize: 12,
                  fontWeight: 800,
                  letterSpacing: '0.09em',
                  textTransform: 'uppercase',
                }}
              >
                THE CORE QUESTION
              </span>
              <span
                style={{
                  color: SHIPKART_THEME.muted,
                  fontSize: 14,
                  fontWeight: 700,
                }}
              >
                Post-Return Reality Check
              </span>
            </div>

            <h2
              style={{
                margin: 0,
                fontSize: 33,
                lineHeight: 1.2,
                fontWeight: 800,
                letterSpacing: '-0.02em',
                color: SHIPKART_THEME.navy,
              }}
            >
              “Why should customers struggle to get their own money back after a{' '}
              <span
                style={{
                  color: SHIPKART_THEME.blue,
                  backgroundColor: '#eff6ff',
                  padding: '1px 8px',
                  borderRadius: 8,
                }}
              >
                valid return
              </span>
              ?”
            </h2>
          </div>

          <div
            style={{
              flexShrink: 0,
              padding: '12px 20px',
              borderRadius: 14,
              backgroundColor: '#fffbeb',
              border: '1px solid #fde68a',
              textAlign: 'right',
            }}
          >
            <div
              style={{
                fontSize: 11,
                fontWeight: 800,
                color: SHIPKART_THEME.amber,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}
            >
              Root Cause
            </div>
            <div
              style={{
                fontSize: 20,
                fontWeight: 900,
                color: SHIPKART_THEME.navy,
              }}
            >
              5 Siloed Parties
            </div>
          </div>
        </div>

        {/* 140..540f: Split Layout (Illustration Left + 5-Step Animated Node Chain Right) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '0.94fr 1.06fr',
            gap: 26,
            flex: 1,
            minHeight: 0,
          }}
        >
          {/* Left Side: Multi-Party Ecosystem Illustration */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <ImageFrame
              imagePath="images/multi_party_ecosystem.jpg"
              alt="Multi-party refund ecosystem connecting customer, merchant, payment gateway, bank, and regulator"
              badge="DISCONNECTED LEDGERS"
              caption="Multi-Party Refund Handoff Ecosystem"
              delayFrames={140}
              zoomDurationFrames={400}
              height={460}
            />

            <RevealBox delayFrames={220} direction="up" distance={20}>
              <div
                style={{
                  backgroundColor: '#ffffff',
                  borderRadius: 16,
                  border: `1px solid ${SHIPKART_THEME.border}`,
                  padding: '16px 22px',
                  boxShadow: '0 10px 24px rgba(15, 35, 58, 0.07)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 16,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: 12,
                      backgroundColor: '#fef2f2',
                      border: '1px solid #fecaca',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Building2 size={22} color={SHIPKART_THEME.red} />
                  </div>
                  <div>
                    <div
                      style={{
                        fontSize: 18,
                        fontWeight: 800,
                        color: SHIPKART_THEME.navy,
                      }}
                    >
                      A Delay at Any Stage Strands the Customer
                    </div>
                    <div
                      style={{
                        fontSize: 14,
                        fontWeight: 500,
                        color: SHIPKART_THEME.muted,
                      }}
                    >
                      Without cross-party orchestration, every handoff becomes an opaque black box.
                    </div>
                  </div>
                </div>
              </div>
            </RevealBox>
          </div>

          {/* Right Side: Interactive 5-Step Animated Node Chain */}
          <RevealBox delayFrames={150} direction="left" distance={30}>
            <div
              style={{
                height: '100%',
                backgroundColor: '#ffffff',
                borderRadius: 20,
                border: `1px solid ${SHIPKART_THEME.border}`,
                boxShadow: '0 16px 36px rgba(15, 35, 58, 0.09)',
                padding: '18px 24px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingBottom: 10,
                  borderBottom: `1px solid ${SHIPKART_THEME.border}`,
                }}
              >
                <span
                  style={{
                    fontSize: 15,
                    fontWeight: 800,
                    color: SHIPKART_THEME.navy,
                    letterSpacing: '0.05em',
                    textTransform: 'uppercase',
                  }}
                >
                  5-Party Refund Handoff Chain
                </span>
                <span
                  style={{
                    padding: '4px 12px',
                    borderRadius: 9999,
                    backgroundColor: '#fffbeb',
                    border: '1px solid #fde68a',
                    color: SHIPKART_THEME.amber,
                    fontSize: 12,
                    fontWeight: 800,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                  }}
                >
                  3 Critical Blind Spots
                </span>
              </div>

              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  flex: 1,
                  paddingTop: 10,
                }}
              >
                {parties.map((party) => {
                  const Icon = party.icon;
                  const gap = party.gapAfter;

                  return (
                    <React.Fragment key={party.step}>
                      <RevealBox delayFrames={party.delay} direction="left" distance={22}>
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '11px 16px',
                            borderRadius: 14,
                            backgroundColor: '#f8fafc',
                            border: `1px solid ${SHIPKART_THEME.border}`,
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                            <div
                              style={{
                                width: 38,
                                height: 38,
                                borderRadius: 11,
                                backgroundColor: party.accent,
                                color: '#ffffff',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                flexShrink: 0,
                              }}
                            >
                              <Icon size={20} color="#ffffff" />
                            </div>
                            <div>
                              <div
                                style={{
                                  fontSize: 18,
                                  fontWeight: 800,
                                  color: SHIPKART_THEME.navy,
                                  lineHeight: 1.2,
                                }}
                              >
                                {party.step}. {party.title}
                              </div>
                              <div
                                style={{
                                  fontSize: 13,
                                  fontWeight: 500,
                                  color: SHIPKART_THEME.muted,
                                }}
                              >
                                {party.role}
                              </div>
                            </div>
                          </div>

                          <span
                            style={{
                              fontSize: 12,
                              fontWeight: 800,
                              color: party.accent,
                              backgroundColor: '#ffffff',
                              border: `1px solid ${SHIPKART_THEME.border}`,
                              padding: '4px 10px',
                              borderRadius: 9999,
                            }}
                          >
                            NODE 0{party.step}
                          </span>
                        </div>
                      </RevealBox>

                      {/* Animated Amber/Red Stall Beacon in Handoff Gap */}
                      {gap ? (
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            paddingLeft: 34,
                            paddingRight: 12,
                            height: 36,
                          }}
                        >
                          <div
                            style={{
                              width: 3,
                              height: '100%',
                              backgroundColor:
                                gap.severity === 'red' ? '#fca5a5' : '#fcd34d',
                            }}
                          />

                          <div
                            style={{
                              opacity: stallReveal,
                              transform: `scale(${
                                gap.severity === 'red' ? beaconScale : 1
                              })`,
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 8,
                              padding: '4px 12px',
                              borderRadius: 9999,
                              backgroundColor:
                                gap.severity === 'red' ? '#fef2f2' : '#fffbeb',
                              border: `1px solid ${
                                gap.severity === 'red' ? '#fca5a5' : '#fcd34d'
                              }`,
                            }}
                          >
                            <span
                              style={{
                                width: 8,
                                height: 8,
                                borderRadius: 9999,
                                backgroundColor:
                                  gap.severity === 'red'
                                    ? SHIPKART_THEME.red
                                    : SHIPKART_THEME.amber,
                                opacity: beaconOpacity,
                              }}
                            />
                            <AlertOctagon
                              size={14}
                              color={
                                gap.severity === 'red'
                                  ? SHIPKART_THEME.red
                                  : SHIPKART_THEME.amber
                              }
                            />
                            <span
                              style={{
                                fontSize: 12,
                                fontWeight: 800,
                                color:
                                  gap.severity === 'red'
                                    ? SHIPKART_THEME.red
                                    : SHIPKART_THEME.amber,
                                letterSpacing: '0.03em',
                              }}
                            >
                              STALL RISK: {gap.label}
                            </span>
                          </div>
                        </div>
                      ) : null}
                    </React.Fragment>
                  );
                })}
              </div>
            </div>
          </RevealBox>
        </div>
      </div>
    </ShipkartStageBackground>
  );
};
