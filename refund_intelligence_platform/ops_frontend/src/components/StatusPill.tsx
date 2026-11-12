import { AlertTriangle, RefreshCw } from 'lucide-react';
import { formatNumericMoney, getStatusBadgeClasses } from '../utils/format';

interface StatusPillProps {
  value: string | null | undefined;
  className?: string;
}

export function StatusPill({ value, className = '' }: StatusPillProps) {
  const display = value && value.trim() ? value : 'UNKNOWN';
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-semibold tracking-tight ${getStatusBadgeClasses(
        display
      )} ${className}`}
    >
      {display}
    </span>
  );
}

interface CurrencyAmountProps {
  amount: string | null | undefined;
  currency: string;
  muted?: boolean;
}

export function CurrencyAmount({ amount, currency, muted = false }: CurrencyAmountProps) {
  const code = (currency || 'USD').toUpperCase();
  return (
    <span
      className={`inline-flex items-baseline gap-1.5 tabular-mono ${
        muted ? 'text-gray-500' : 'text-gray-900'
      }`}
    >
      <span className="font-bold">{formatNumericMoney(amount, code)}</span>
      <span
        className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
          code === 'INR'
            ? 'bg-blue-50 text-shipkart-blue border border-blue-200'
            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
        }`}
      >
        {code}
      </span>
    </span>
  );
}

interface ApiErrorBannerProps {
  message: string;
  status?: number;
  onRetry?: () => void;
}

export function ApiErrorBanner({ message, status, onRetry }: ApiErrorBannerProps) {
  const isAuthError = status === 401 || status === 403;
  return (
    <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-900">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
          <div>
            <p className="font-bold">
              {isAuthError ? 'Platform Session Authorization Required' : 'Service Request Error'}
            </p>
            <p className="mt-0.5 text-xs text-red-800">{message}</p>
          </div>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded border border-red-300 bg-white px-3 py-1.5 text-xs font-semibold text-red-900 hover:bg-red-100"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
