import React from 'react';
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { Eye, ShieldCheck, Sparkles, Zap } from 'lucide-react';

export const Scene7ClosingGoal: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const heroSpring = spring({
    frame,
    fps,
    config: { damping: 20, stiffness: 180, mass: 0.85 },
  });
  const heroOpacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const heroY = interpolate(heroSpring, [0, 1], [24, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const pillars = [
    {
      title: 'Accountable',
      subtitle: 'Clear ownership across every step',
      description:
        'Full audit trail from return pickup through gateway settlement and human-approved actions.',
      enterFrame: 18,
      accent: '#2874f0',
      subtitleColor: '#2874f0',
      iconWellClass: 'bg-[#eff6ff] border-[#2874f0]/20',
      badge: '01 • OWNERSHIP',
      icon: <ShieldCheck className="w-8 h-8 text-[#2874f0]" />,
    },
    {
      title: 'Transparent',
      subtitle: 'Real-time root-cause clarity',
      description:
        'Verified ARN & manifest evidence keeps customers and operators informed without guesswork.',
      enterFrame: 38,
      accent: '#eab308',
      subtitleColor: '#a16207',
      iconWellClass: 'bg-amber-50 border-amber-200',
      badge: '02 • VISIBILITY',
      icon: <Eye className="w-8 h-8 text-[#ca8a04]" />,
    },
    {
      title: 'Faster',
      subtitle: 'Proactive autonomous resolution',
      description:
        'AI agents detect bottlenecks early and dispatch resolution workflows in minutes, not weeks.',
      enterFrame: 58,
      accent: '#16a34a',
      subtitleColor: '#16a34a',
      iconWellClass: 'bg-emerald-50 border-emerald-200',
      badge: '03 • VELOCITY',
      icon: <Zap className="w-8 h-8 text-[#16a34a]" />,
    },
  ];

  return (
    <AbsoluteFill className="bg-[#f8fafc] text-[#0f233a] px-20 pt-16 pb-[176px] flex flex-col justify-center gap-12 overflow-hidden">
      {/* Hero Title Section */}
      <div
        className="relative z-10 text-center max-w-[1260px] mx-auto pb-8 border-b border-slate-200"
        style={{
          opacity: heroOpacity,
          transform: `translateY(${heroY}px)`,
        }}
      >
        <div className="inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full bg-[#eff6ff] border border-[#2874f0]/25 text-[#2874f0] text-xs font-extrabold tracking-widest uppercase mb-5">
          <Sparkles className="w-4 h-4 text-[#2874f0]" />
          <span>Our Commitment</span>
        </div>

        <h1 className="text-[64px] leading-[1.1] font-extrabold tracking-tight text-[#0f233a]">
          Make Every Refund{' '}
          <span className="text-[#2874f0]">Accountable</span>,{' '}
          <span className="text-[#16a34a]">Transparent</span>, and{' '}
          <span className="text-[#fb641b]">Faster</span>.
        </h1>
      </div>

      {/* 3 Spotlight Cards */}
      <div className="relative z-10 grid grid-cols-3 gap-8 pt-2">
        {pillars.map((pillar) => {
          const localF = Math.max(0, frame - pillar.enterFrame);
          const cardSpring = spring({
            frame: localF,
            fps,
            config: { damping: 18, stiffness: 185, mass: 0.8 },
          });
          const opacity = interpolate(localF, [0, 16], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });
          const slideY = interpolate(cardSpring, [0, 1], [36, 0], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });

          return (
            <div
              key={pillar.title}
              className="rounded-3xl bg-white border border-slate-200 p-8 shadow-sm flex flex-col justify-between relative overflow-hidden"
              style={{
                opacity,
                transform: `translateY(${slideY}px)`,
              }}
            >
              {/* Top 4px Solid Accent Rule */}
              <div
                className="absolute top-0 left-0 right-0 h-1"
                style={{ backgroundColor: pillar.accent }}
              />

              <div>
                <div className="flex items-center justify-between mb-6">
                  <div
                    className={`w-16 h-16 rounded-2xl border flex items-center justify-center ${pillar.iconWellClass}`}
                  >
                    {pillar.icon}
                  </div>
                  <span className="text-xs font-mono font-bold tracking-widest text-slate-500 px-3 py-1 rounded-full bg-[#f8fafc] border border-slate-200">
                    {pillar.badge}
                  </span>
                </div>

                <h2 className="text-[34px] font-extrabold text-[#0f233a] tracking-tight">
                  {pillar.title}
                </h2>
                <p
                  className="text-[17px] font-semibold mt-1"
                  style={{ color: pillar.subtitleColor }}
                >
                  {pillar.subtitle}
                </p>
                <p className="text-[17px] leading-relaxed text-slate-600 mt-4">
                  {pillar.description}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
