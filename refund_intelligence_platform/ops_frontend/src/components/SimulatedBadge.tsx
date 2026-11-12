import { FlaskConical, Scale } from 'lucide-react';

interface SimulatedBadgeProps {
  label?: string;
  compact?: boolean;
}

export function SimulatedBadge({ label = 'Simulated', compact = false }: SimulatedBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border border-amber-300 bg-amber-50 font-semibold uppercase tracking-wider text-amber-800 ${
        compact ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-0.5 text-[11px]'
      }`}
      title="Synthetic simulator data — not live external banking/carrier/legal authority"
    >
      <FlaskConical className={compact ? 'h-2.5 w-2.5' : 'h-3 w-3'} />
      {label}
    </span>
  );
}

export function RegulatoryDisclaimerBanner() {
  return (
    <div className="flex items-start gap-3 rounded border border-blue-200 bg-blue-50/70 px-4 py-3 text-sm text-gray-800">
      <Scale className="mt-0.5 h-4 w-4 shrink-0 text-shipkart-blue" />
      <div className="flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-bold text-gray-900">Simulated Regulatory Rules Evaluation</span>
          <SimulatedBadge compact />
        </div>
        <p className="mt-0.5 text-xs text-gray-600">
          Software-based rules evaluation simulation, not legal advice. Incomplete transaction
          context returns <span className="font-semibold text-gray-900">UNKNOWN</span> or{' '}
          <span className="font-semibold text-gray-900">MANUAL_REVIEW_REQUIRED</span> without
          assuming compliance.
        </p>
      </div>
    </div>
  );
}
