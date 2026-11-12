import React from 'react';
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {
  ArrowDown,
  Bot,
  CheckCircle2,
  Clock,
  Lock,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserCheck,
  XCircle,
} from 'lucide-react';

export const Scene6HumanApproval: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headerSpring = spring({
    frame,
    fps,
    config: { damping: 20, stiffness: 190, mass: 0.8 },
  });
  const headerOpacity = interpolate(frame, [0, 16], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const headerY = interpolate(headerSpring, [0, 1], [-16, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // Left card: Diagnostic Comparison (focuses in 0..180f, stays crisp)
  const leftSpring = spring({
    frame: Math.max(0, frame - 8),
    fps,
    config: { damping: 20, stiffness: 175, mass: 0.85 },
  });
  const leftOpacity = interpolate(frame, [8, 26], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const leftX = interpolate(leftSpring, [0, 1], [-28, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const passiveReveal = interpolate(frame, [16, 36], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const agenticReveal = spring({
    frame: Math.max(0, frame - 52),
    fps,
    config: { damping: 18, stiffness: 185, mass: 0.8 },
  });
  const agenticOpacity = interpolate(frame, [52, 72], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // Right card: REF-001 Approval Gate Card (130..345f)
  const rightEnterFrame = 122;
  const rightLocalFrame = Math.max(0, frame - rightEnterFrame);
  const rightSpring = spring({
    frame: rightLocalFrame,
    fps,
    config: { damping: 19, stiffness: 180, mass: 0.85 },
  });
  const rightOpacity = interpolate(frame, [rightEnterFrame, rightEnterFrame + 20], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const rightX = interpolate(rightSpring, [0, 1], [44, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // Steps inside REF-001 Approval Gate Card
  const step1Spring = spring({
    frame: Math.max(0, frame - 145),
    fps,
    config: { damping: 20, stiffness: 200, mass: 0.75 },
  });
  const step1Opacity = interpolate(frame, [145, 162], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const step2Spring = spring({
    frame: Math.max(0, frame - 172),
    fps,
    config: { damping: 18, stiffness: 210, mass: 0.75 },
  });
  const step2Opacity = interpolate(frame, [172, 190], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // Approval transition around frame 230
  const isApproved = frame >= 230;
  const approvalProgress = spring({
    frame: Math.max(0, frame - 230),
    fps,
    config: { damping: 16, stiffness: 220, mass: 0.7 },
  });
  const step3Opacity = interpolate(frame, [228, 246], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // Button press feedback between frames 214..232
  const buttonPressScale =
    frame >= 216 && frame < 230
      ? interpolate(frame, [216, 223, 230], [1, 0.94, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        })
      : 1;

  const gatePulse = (Math.sin(frame * 0.16) + 1) * 0.5;

  return (
    <AbsoluteFill className="bg-[#f4f6f9] text-[#0f233a] px-16 pt-10 pb-[160px] flex flex-col justify-between overflow-hidden">
      {/* Top Differentiator Banner */}
      <div
        className="relative z-10 flex items-center justify-between bg-white text-[#0f233a] rounded-2xl border border-slate-200 border-l-[6px] border-l-[#2874f0] px-8 py-4 shadow-sm"
        style={{
          opacity: headerOpacity,
          transform: `translateY(${headerY}px)`,
        }}
      >
        <div className="flex items-center gap-4">
          <span className="px-3.5 py-1 rounded-full bg-[#ffe11b] text-[#0f233a] text-xs font-extrabold tracking-widest uppercase">
            Key Differentiator
          </span>
          <h2 className="text-[26px] font-bold tracking-tight text-[#0f233a]">
            Actionable Resolution with Human-in-the-Loop Control
          </h2>
        </div>

        <div className="flex items-center gap-2.5 text-sm font-semibold text-[#2874f0] bg-[#eff6ff] px-4 py-1.5 rounded-xl border border-[#2874f0]/25">
          <Lock className="w-4 h-4 text-[#2874f0]" />
          <span>Policy-Gated Autonomous Execution</span>
        </div>
      </div>

      {/* Main Two-Column Content */}
      <div className="relative z-10 grid grid-cols-12 gap-8 flex-1 mt-6 min-h-0 items-stretch">
        {/* Left Column: Diagnostic Comparison Card */}
        <div
          className="col-span-5 bg-white rounded-3xl border border-slate-200 shadow-sm p-7 flex flex-col justify-between"
          style={{
            opacity: leftOpacity,
            transform: `translateX(${leftX}px)`,
          }}
        >
          <div>
            <div className="flex items-center justify-between mb-5">
              <span className="text-xs font-bold uppercase tracking-widest text-[#2874f0]">
                Diagnostic Comparison
              </span>
              <span className="text-xs font-mono text-slate-400">
                TRACKING vs RESOLUTION
              </span>
            </div>

            {/* Passive Tracker Block */}
            <div
              className="rounded-2xl bg-[#f8fafc] border border-slate-200 p-5"
              style={{ opacity: passiveReveal }}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-xl bg-amber-100 border border-amber-300 flex items-center justify-center">
                    <Clock className="w-5 h-5 text-amber-700" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-slate-700">
                      Passive Tracker
                    </h3>
                    <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">
                      Wait &amp; Hope
                    </p>
                  </div>
                </div>
                <span className="px-3 py-1 rounded-full bg-slate-200 text-slate-600 text-xs font-bold">
                  NO ACTION
                </span>
              </div>

              <div className="space-y-2 text-sm text-slate-600 mt-3">
                <div className="flex items-center gap-2">
                  <XCircle className="w-4 h-4 text-slate-400 shrink-0" />
                  <span>Only displays generic &ldquo;Refund Pending&rdquo;</span>
                </div>
                <div className="flex items-center gap-2">
                  <XCircle className="w-4 h-4 text-slate-400 shrink-0" />
                  <span>No root-cause inspection across gateway/bank</span>
                </div>
                <div className="flex items-center gap-2">
                  <XCircle className="w-4 h-4 text-slate-400 shrink-0" />
                  <span>Customer left chasing support tickets</span>
                </div>
              </div>
            </div>

            {/* Transition Arrow */}
            <div className="flex justify-center my-3">
              <div className="w-9 h-9 rounded-full bg-[#eff6ff] border border-[#2874f0]/30 flex items-center justify-center">
                <ArrowDown className="w-5 h-5 text-[#2874f0]" />
              </div>
            </div>

            {/* Agentic Resolution Block */}
            <div
              className="rounded-2xl bg-[#eff6ff] text-[#0f233a] border-2 border-[#2874f0] p-5 shadow-sm"
              style={{
                opacity: agenticOpacity,
                transform: `translateY(${interpolate(agenticReveal, [0, 1], [16, 0], {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                })}px)`,
              }}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-xl bg-[#2874f0] flex items-center justify-center">
                    <Sparkles className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-[#0f233a]">
                      Agentic Resolution
                    </h3>
                    <p className="text-xs font-semibold uppercase tracking-wide text-[#2874f0]">
                      Root Cause → Action Plan
                    </p>
                  </div>
                </div>
                <span className="px-3 py-1 rounded-full bg-[#2874f0] text-white text-xs font-bold">
                  ACTIVE ENGINE
                </span>
              </div>

              <div className="space-y-2.5 text-sm text-[#0f233a] font-medium mt-3">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-[#16a34a] shrink-0" />
                  <span>Diagnoses exact blocker (gateway capture hold)</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-[#16a34a] shrink-0" />
                  <span>Builds verifiable action plan &amp; payload</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-[#2874f0] shrink-0" />
                  <span>Requires human approval on financial execution</span>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500 font-medium">
            <span>Zero blind automation</span>
            <span className="text-[#0f233a] font-bold">
              Safe • Auditable • Fast
            </span>
          </div>
        </div>

        {/* Right Column: Shipkart Ops UI REF-001 Approval Gate Card */}
        <div
          className="col-span-7 bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden flex flex-col justify-between"
          style={{
            opacity: rightOpacity,
            transform: `translateX(${rightX}px)`,
          }}
        >
          {/* Shipkart Ops Card Header */}
          <div className="bg-white border-b border-slate-200 px-7 py-5 text-[#0f233a] flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="px-3.5 py-1.5 rounded-lg bg-[#2874f0] font-mono font-extrabold text-sm tracking-wider text-white">
                REF-001
              </div>
              <div>
                <div className="text-xl font-bold tracking-tight text-[#0f233a] flex items-center gap-2.5">
                  <span>Approval Gate Card</span>
                  <span className="text-xs font-mono px-2.5 py-0.5 rounded bg-[#f1f5f9] border border-slate-200 text-[#0f233a]">
                    Order #26
                  </span>
                </div>
                <p className="text-sm text-slate-500 mt-0.5">
                  Order #26 • PayPal Capture Refund
                </p>
              </div>
            </div>

            {/* Live Status Badge */}
            {isApproved ? (
              <div
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#16a34a] text-white text-xs font-extrabold uppercase tracking-wider shadow-sm"
                style={{
                  transform: `scale(${interpolate(approvalProgress, [0, 1], [0.9, 1], {
                    extrapolateLeft: 'clamp',
                    extrapolateRight: 'clamp',
                  })})`,
                }}
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>Approved &amp; Settled</span>
              </div>
            ) : (
              <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#ffe11b] text-[#0f233a] text-xs font-extrabold uppercase tracking-wider border border-amber-300">
                <span
                  className="w-2.5 h-2.5 rounded-full bg-[#fb641b]"
                  style={{ opacity: 0.45 + gatePulse * 0.55 }}
                />
                <span>Awaiting Human Gate</span>
              </div>
            )}
          </div>

          {/* 3 Execution Gate Steps */}
          <div className="p-7 flex-1 flex flex-col justify-between gap-4">
            {/* Step 1: AI Proposed Action */}
            <div
              className="rounded-2xl border border-[#2874f0]/25 bg-[#eff6ff] px-6 py-4 flex items-center justify-between gap-4"
              style={{
                opacity: step1Opacity,
                transform: `translateY(${interpolate(step1Spring, [0, 1], [16, 0], {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                })}px)`,
              }}
            >
              <div className="flex items-center gap-4">
                <div className="w-11 h-11 rounded-xl bg-[#2874f0] text-white flex items-center justify-center shrink-0">
                  <Bot className="w-6 h-6" />
                </div>
                <div>
                  <div className="text-xs font-bold uppercase tracking-wider text-[#2874f0]">
                    Step 1 • Autonomous Diagnosis
                  </div>
                  <div className="text-[19px] font-bold text-[#0f233a]">
                    AI Proposed Action: Issue PayPal Capture Refund
                  </div>
                </div>
              </div>
              <span className="px-3 py-1 rounded-lg bg-white border border-[#2874f0]/25 text-xs font-mono font-bold text-[#2874f0] shrink-0">
                PAYLOAD READY
              </span>
            </div>

            {/* Step 2: HUMAN-IN-THE-LOOP GATE */}
            <div
              className="rounded-2xl border-2 px-6 py-4 flex items-center justify-between gap-4"
              style={{
                opacity: step2Opacity,
                transform: `translateY(${interpolate(step2Spring, [0, 1], [16, 0], {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                })}px)`,
                backgroundColor: '#fef9c3',
                borderColor: isApproved ? '#eab308' : '#facc15',
              }}
            >
              <div className="flex items-center gap-4">
                <div className="w-11 h-11 rounded-xl bg-[#ffe11b] border border-amber-300 text-[#0f233a] flex items-center justify-center shrink-0">
                  <ShieldAlert className="w-6 h-6" />
                </div>
                <div>
                  <div className="text-xs font-extrabold uppercase tracking-wider text-amber-800">
                    Step 2 • Policy Safeguard
                  </div>
                  <div className="text-[18px] font-bold text-[#0f233a] font-mono">
                    HUMAN-IN-THE-LOOP GATE:{' '}
                    <span className="px-2 py-0.5 rounded bg-[#0f233a] text-[#ffe11b] text-base">
                      requires_approval = true
                    </span>
                  </div>
                </div>
              </div>

              {/* Action Button Preview */}
              <div
                className="px-4 py-2.5 rounded-xl font-bold text-sm flex items-center gap-2 shrink-0 shadow-sm"
                style={{
                  transform: `scale(${buttonPressScale})`,
                  backgroundColor: isApproved ? '#16a34a' : '#2874f0',
                  color: '#ffffff',
                }}
              >
                <UserCheck className="w-4 h-4 text-[#ffe11b]" />
                <span>{isApproved ? 'Approved' : 'Approve Refund'}</span>
              </div>
            </div>

            {/* Step 3: Merchant Approved -> PayPal Bridge -> Settled */}
            <div
              className="rounded-2xl border-2 px-6 py-4 flex items-center justify-between gap-4"
              style={{
                opacity: isApproved ? step3Opacity : 0.45,
                backgroundColor: isApproved ? '#f0fdf4' : '#f8fafc',
                borderColor: isApproved ? '#16a34a' : '#e2e8f0',
                transform: `translateY(${interpolate(approvalProgress, [0, 1], [12, 0], {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                })}px)`,
              }}
            >
              <div className="flex items-center gap-4">
                <div
                  className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0"
                  style={{
                    backgroundColor: isApproved ? '#16a34a' : '#94a3b8',
                    color: '#ffffff',
                  }}
                >
                  <ShieldCheck className="w-6 h-6" />
                </div>
                <div>
                  <div
                    className="text-xs font-bold uppercase tracking-wider"
                    style={{ color: isApproved ? '#16a34a' : '#64748b' }}
                  >
                    Step 3 • Verified Execution
                  </div>
                  <div className="text-[18px] font-bold text-[#0f233a]">
                    Merchant Approved ✓ → Executed via PayPal Bridge → Refund
                    Settled
                  </div>
                </div>
              </div>

              <span
                className="px-3.5 py-1.5 rounded-full text-xs font-extrabold uppercase tracking-wider shrink-0"
                style={{
                  backgroundColor: isApproved ? '#16a34a' : '#e2e8f0',
                  color: isApproved ? '#ffffff' : '#64748b',
                }}
              >
                {isApproved ? 'SETTLED ✓' : 'PENDING GATE'}
              </span>
            </div>
          </div>

          {/* Ops Audit Footer */}
          <div className="bg-[#f8fafc] px-7 py-3 border-t border-slate-200 flex items-center justify-between text-xs font-mono text-slate-600 tabular-nums">
            <span>AUDIT_LOG: REF-001 • ORDER #26 • GATEWAY: PAYPAL_REST_V2</span>
            <span className="font-bold text-[#0f233a]">
              {isApproved
                ? 'STATUS: 200_REFUND_COMPLETED'
                : 'STATUS: HELD_FOR_OPERATOR'}
            </span>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
