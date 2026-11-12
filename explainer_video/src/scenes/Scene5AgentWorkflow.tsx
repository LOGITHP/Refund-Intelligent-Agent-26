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
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileSearch,
  Megaphone,
  Radio,
  SearchCheck,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';

interface ActionCardConfig {
  step: string;
  title: string;
  description: string;
  enterFrame: number;
  activeStart: number;
  activeEnd: number;
  accentColor: string;
  badgeText: string;
  icon: React.ReactNode;
}

export const Scene5AgentWorkflow: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headerSpring = spring({
    frame,
    fps,
    config: { damping: 20, stiffness: 180, mass: 0.8 },
  });

  const headerOpacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const headerY = interpolate(headerSpring, [0, 1], [-18, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const leftCardSpring = spring({
    frame: Math.max(0, frame - 8),
    fps,
    config: { damping: 20, stiffness: 170, mass: 0.85 },
  });

  const leftCardOpacity = interpolate(frame, [8, 28], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const leftCardScale = interpolate(leftCardSpring, [0, 1], [0.95, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const actionCards: ActionCardConfig[] = [
    {
      step: '01',
      title: 'Monitor Lifecycle',
      description: 'Tracks Carrier, Gateway & Bank signals continuously',
      enterFrame: 6,
      activeStart: 0,
      activeEnd: 180,
      accentColor: '#2874f0',
      badgeText: 'TELEMETRY ACTIVE',
      icon: <Radio className="w-6 h-6 text-white" />,
    },
    {
      step: '02',
      title: 'Identify Root Cause',
      description: 'Pinpoints settlement holds, pickup gaps, or SLA breaches',
      enterFrame: 140,
      activeStart: 140,
      activeEnd: 280,
      accentColor: '#2874f0',
      badgeText: 'ROOT CAUSE DIAGNOSIS',
      icon: <SearchCheck className="w-6 h-6 text-white" />,
    },
    {
      step: '03',
      title: 'Collect Evidence & Communicate',
      description:
        'Gathers signed manifests/ARN proof & updates customers transparently',
      enterFrame: 220,
      activeStart: 220,
      activeEnd: 360,
      accentColor: '#16a34a',
      badgeText: 'EVIDENCE PACKET READY',
      icon: <FileSearch className="w-6 h-6 text-white" />,
    },
    {
      step: '04',
      title: 'Escalate Unresolved Cases',
      description:
        'Dispatches structured complaints to PayPal / Issuing Bank / Regulatory authorities',
      enterFrame: 310,
      activeStart: 310,
      activeEnd: 480,
      accentColor: '#fb641b',
      badgeText: 'AUTHORITY ESCALATION',
      icon: <Megaphone className="w-6 h-6 text-white" />,
    },
  ];

  const orbitAgents = [
    {
      name: 'Investigator Agent',
      role: 'Telemetry & Root Cause',
      startFrame: 18,
      activeRange: [0, 260] as const,
      dotColor: '#2874f0',
      positionClass: 'top-5 left-5',
      floatPhase: 0,
    },
    {
      name: 'Auditor Agent',
      role: 'ARN & Manifest Proof',
      startFrame: 34,
      activeRange: [200, 360] as const,
      dotColor: '#16a34a',
      positionClass: 'top-5 right-5',
      floatPhase: 2.1,
    },
    {
      name: 'Escalation Agent',
      role: 'Gateway & Bank Dispatch',
      startFrame: 50,
      activeRange: [300, 480] as const,
      dotColor: '#fb641b',
      positionClass: 'bottom-5 left-1/2',
      floatPhase: 4.2,
      centerX: true,
    },
  ];

  const pulseProgress = (Math.sin(frame * 0.14) + 1) * 0.5;

  return (
    <AbsoluteFill className="bg-[#f4f6f9] text-[#0f233a] px-16 pt-10 pb-[160px] flex flex-col justify-between overflow-hidden">
      {/* Top Comparison Header */}
      <div
        className="relative z-10 flex items-center justify-between gap-6 bg-white rounded-2xl border border-slate-200 shadow-sm px-8 py-4"
        style={{
          opacity: headerOpacity,
          transform: `translateY(${headerY}px)`,
        }}
      >
        <div className="flex items-center gap-3">
          <span className="px-3.5 py-1 rounded-full bg-[#eff6ff] border border-[#2874f0]/25 text-[#2874f0] text-xs font-bold tracking-widest uppercase">
            Autonomous Monitoring
          </span>
          <span className="text-lg font-bold text-[#0f233a]">
            Active Agentic Lifecycle Workflow
          </span>
        </div>

        <div className="flex items-center gap-4">
          {/* Old World Badge */}
          <div className="flex items-center gap-2.5 px-4 py-2 rounded-xl bg-amber-50 border border-amber-200 text-slate-600">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <div className="flex items-center gap-2 text-sm">
              <span className="font-semibold uppercase tracking-wide text-amber-800 text-xs">
                Old World:
              </span>
              <span className="font-medium text-slate-700 line-through decoration-amber-500/70">
                Static Refund Pending Label
              </span>
            </div>
          </div>

          <ArrowRight className="w-5 h-5 text-[#2874f0] shrink-0" />

          {/* Agentic Intelligence Badge */}
          <div className="flex items-center gap-2.5 px-5 py-2 rounded-xl bg-[#2874f0] text-white shadow-sm">
            <Sparkles className="w-4 h-4 text-[#ffe11b] shrink-0" />
            <div className="flex items-center gap-2 text-sm">
              <span className="font-bold uppercase tracking-wide text-[#ffe11b] text-xs">
                Agentic Intelligence:
              </span>
              <span className="font-semibold">
                Active Lifecycle Resolution Engine
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="relative z-10 grid grid-cols-12 gap-8 flex-1 mt-6 min-h-0 items-stretch">
        {/* Left Panel: Shield Illustration + Animated Agent Orbit Callouts */}
        <div
          className="col-span-5 flex flex-col justify-between bg-white rounded-3xl border border-slate-200 shadow-sm p-5 relative overflow-hidden"
          style={{
            opacity: leftCardOpacity,
            transform: `scale(${leftCardScale})`,
          }}
        >
          <div className="relative flex-1 rounded-2xl overflow-hidden border border-slate-200 bg-[#f1f5f9]">
            <Img
              src={staticFile('images/agentic_ai_shield.jpg')}
              className="w-full h-full object-cover"
              style={{
                transform: `scale(${interpolate(frame, [0, 480], [1.02, 1.08], {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                })})`,
              }}
            />

            {/* Animated Status Orbit Callouts */}
            {orbitAgents.map((agent) => {
              const localF = Math.max(0, frame - agent.startFrame);
              const pop = spring({
                frame: localF,
                fps,
                config: { damping: 18, stiffness: 200, mass: 0.7 },
              });
              const opacity = interpolate(localF, [0, 12], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
              });
              const isActive =
                frame >= agent.activeRange[0] && frame <= agent.activeRange[1];
              const floatY = Math.sin(frame * 0.08 + agent.floatPhase) * 3.5;
              const xOffset = agent.centerX ? '-50%' : '0px';

              return (
                <div
                  key={agent.name}
                  className={`absolute ${agent.positionClass} rounded-xl px-3.5 py-2.5 bg-white/95 border text-[#0f233a] shadow-md flex items-center gap-2.5`}
                  style={{
                    borderColor: isActive ? agent.dotColor : '#e2e8f0',
                    opacity,
                    transform: `translate(${xOffset}, ${floatY}px) scale(${interpolate(
                      pop,
                      [0, 1],
                      [0.86, 1],
                      {
                        extrapolateLeft: 'clamp',
                        extrapolateRight: 'clamp',
                      },
                    )})`,
                  }}
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{
                      backgroundColor: agent.dotColor,
                      opacity: isActive ? 0.65 + pulseProgress * 0.35 : 0.75,
                    }}
                  />
                  <div className="leading-tight">
                    <div className="text-xs font-bold text-[#0f233a] whitespace-nowrap">
                      {agent.name}
                    </div>
                    <div className="text-[11px] text-slate-500 whitespace-nowrap">
                      {agent.role}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Bottom Shield Telemetry Strip */}
          <div className="mt-4 flex items-center justify-between px-4 py-2.5 rounded-xl bg-[#f8fafc] border border-slate-200 border-t text-[#0f233a]">
            <div className="flex items-center gap-2.5">
              <ShieldCheck className="w-5 h-5 text-[#2874f0]" />
              <span className="text-sm font-semibold text-[#0f233a]">
                Autonomous Refund Mesh
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs font-mono font-semibold text-[#2874f0] tabular-nums">
              <Activity className="w-4 h-4 text-[#16a34a]" />
              <span>3 AGENTS ONLINE</span>
            </div>
          </div>
        </div>

        {/* Right Panel: 4 Sequential Action Cards */}
        <div className="col-span-7 flex flex-col justify-between gap-4">
          {actionCards.map((card) => {
            const localF = Math.max(0, frame - card.enterFrame);
            const cardSpring = spring({
              frame: localF,
              fps,
              config: { damping: 20, stiffness: 190, mass: 0.75 },
            });

            const isVisible = frame >= card.enterFrame;
            const opacity = isVisible
              ? interpolate(localF, [0, 14], [0, 1], {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                })
              : 0.16;

            const slideX = isVisible
              ? interpolate(cardSpring, [0, 1], [36, 0], {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                })
              : 24;

            const isCurrentlyActive =
              frame >= card.activeStart && frame <= card.activeEnd;
            const isCompleted = frame > card.activeEnd;

            const progressFill = interpolate(
              frame,
              [card.activeStart, card.activeEnd],
              [0, 100],
              { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
            );

            return (
              <div
                key={card.step}
                className="relative flex-1 rounded-2xl bg-white border-2 px-7 py-5 shadow-sm flex flex-col justify-center overflow-hidden"
                style={{
                  opacity,
                  transform: `translateX(${slideX}px)`,
                  borderColor: isCurrentlyActive
                    ? card.accentColor
                    : isCompleted
                      ? '#16a34a'
                      : '#e2e8f0',
                  boxShadow: isCurrentlyActive
                    ? '0 4px 12px -2px rgba(15, 35, 58, 0.08)'
                    : '0 1px 2px 0 rgba(15, 35, 58, 0.04)',
                }}
              >
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-5">
                    {/* Step Icon Box */}
                    <div
                      className="w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 shadow-md"
                      style={{
                        backgroundColor: isCompleted
                          ? '#16a34a'
                          : card.accentColor,
                      }}
                    >
                      {card.icon}
                    </div>

                    <div>
                      <div className="flex items-center gap-3">
                        <span
                          className="text-xs font-mono font-bold px-2.5 py-0.5 rounded-md tabular-nums"
                          style={{
                            backgroundColor: isCurrentlyActive
                              ? `${card.accentColor}1A`
                              : '#f1f5f9',
                            color: isCurrentlyActive
                              ? card.accentColor
                              : '#0f233a',
                          }}
                        >
                          STEP {card.step}
                        </span>
                        <h3 className="text-[24px] font-bold text-[#0f233a] leading-tight">
                          {card.title}
                        </h3>
                      </div>
                      <p className="text-[17px] text-slate-600 mt-1 font-medium">
                        {card.description}
                      </p>
                    </div>
                  </div>

                  {/* Right Status Pill */}
                  <div className="shrink-0">
                    {isCompleted ? (
                      <div className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full bg-green-50 border border-green-200 text-[#16a34a] text-xs font-bold tracking-wide">
                        <CheckCircle2 className="w-4 h-4" />
                        <span>VERIFIED</span>
                      </div>
                    ) : isCurrentlyActive ? (
                      <div
                        className="flex items-center gap-2 px-3.5 py-1.5 rounded-full text-white text-xs font-bold tracking-wide"
                        style={{ backgroundColor: card.accentColor }}
                      >
                        <span
                          className="w-2 h-2 rounded-full bg-[#ffe11b]"
                          style={{
                            opacity: 0.55 + pulseProgress * 0.45,
                          }}
                        />
                        <span>{card.badgeText}</span>
                      </div>
                    ) : (
                      <div className="px-3.5 py-1.5 rounded-full bg-slate-100 text-slate-400 text-xs font-semibold tracking-wide">
                        QUEUED
                      </div>
                    )}
                  </div>
                </div>

                {/* Bottom progress bar per card */}
                <div className="mt-3.5 h-1.5 w-full rounded-full bg-slate-100 overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${progressFill}%`,
                      backgroundColor: isCompleted
                        ? '#16a34a'
                        : card.accentColor,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
