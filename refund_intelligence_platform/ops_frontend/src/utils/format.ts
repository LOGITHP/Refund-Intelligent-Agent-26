export function formatNumericMoney(
  amount: string | null | undefined,
  currency: string
): string {
  if (amount === null || amount === undefined || amount.trim() === '') {
    return `— ${currency.toUpperCase()}`;
  }
  const clean = amount.trim();
  const [intPartRaw, fracPartRaw] = clean.split('.');
  const isNegative = intPartRaw.startsWith('-');
  const digits = isNegative ? intPartRaw.slice(1) : intPartRaw;
  const formattedInt = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const frac = fracPartRaw !== undefined ? `.${fracPartRaw.padEnd(2, '0').slice(0, 2)}` : '.00';
  const symbol = currency.toUpperCase() === 'INR' ? '₹' : currency.toUpperCase() === 'USD' ? '$' : '';
  return `${isNegative ? '-' : ''}${symbol}${formattedInt}${frac}`;
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
}

export function shortId(value: string | null | undefined, chars = 8): string {
  if (!value) {
    return '—';
  }
  if (value.length <= chars + 4) {
    return value;
  }
  return `${value.slice(0, chars)}…`;
}

export function getStatusBadgeClasses(status: string | null | undefined): string {
  const s = (status || '').toUpperCase();
  if (
    s.includes('COMPLETED') ||
    s.includes('HEALTHY') ||
    s === 'OK' ||
    s === 'CONFIGURED' ||
    s === 'MERCHANT_DIRECT' ||
    s.includes('PASSED') ||
    s.includes('APPROVED') ||
    s.includes('POSTED') ||
    s === 'APPLICABLE' ||
    s === 'RESOLVED' ||
    s === 'HIGH' ||
    s === 'NONE'
  ) {
    return 'bg-emerald-50 text-emerald-800 border-emerald-200';
  }
  if (
    s.includes('PENDING') ||
    s.includes('INVESTIGATING') ||
    s.includes('RUNNING') ||
    s.includes('IN_TRANSIT') ||
    s.includes('DEGRADED') ||
    s.includes('DELAYED') ||
    s.includes('POTENTIALLY') ||
    s.includes('MANUAL_REVIEW') ||
    s === 'PROPOSED' ||
    s === 'MEDIUM' ||
    s === 'ISSUER_OR_BANK'
  ) {
    return 'bg-amber-50 text-amber-800 border-amber-200';
  }
  if (
    s.includes('FAILED') ||
    s.includes('REJECTED') ||
    s.includes('LOST') ||
    s.includes('MISMATCH') ||
    s.includes('UNAVAILABLE') ||
    s === 'UNCONFIGURED' ||
    s.includes('DOWN') ||
    s.includes('OVERDUE') ||
    s.includes('STALLED') ||
    s.includes('CRITICAL') ||
    s === 'OPEN' ||
    s.includes('DUPLICATE')
  ) {
    return 'bg-rose-50 text-rose-800 border-rose-200';
  }
  if (s === 'NOT_ESTIMABLE' || s === 'UNKNOWN' || s === 'INSUFFICIENT_EVIDENCE') {
    return 'bg-slate-100 text-slate-700 border-slate-300';
  }
  return 'bg-sky-50 text-sky-800 border-sky-200';
}

export function getDelayOwnerClasses(owner: string): string {
  switch (owner.toUpperCase()) {
    case 'CARRIER':
      return 'bg-orange-50 text-orange-800 border-orange-200';
    case 'MERCHANT':
      return 'bg-indigo-50 text-indigo-800 border-indigo-200';
    case 'PAYPAL':
      return 'bg-sky-50 text-sky-800 border-sky-200';
    case 'ISSUER_OR_BANK':
      return 'bg-amber-50 text-amber-900 border-amber-300';
    case 'CUSTOMER':
      return 'bg-purple-50 text-purple-800 border-purple-200';
    case 'NONE':
      return 'bg-emerald-50 text-emerald-800 border-emerald-200';
    default:
      return 'bg-slate-100 text-slate-700 border-slate-300';
  }
}
