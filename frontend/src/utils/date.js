import { getTimezone } from './timezone';

// Backend stores timestamps as UTC but SQLAlchemy on SQLite serializes them as
// naive ISO strings (no 'Z'). new Date() would interpret those as local time,
// shifting the displayed value by the user's UTC offset. parseUtc forces UTC
// interpretation so toLocaleString below converts to the right zone.
export function parseUtc(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value);
  return new Date(hasTz ? value : value + 'Z');
}

function withTimezone(opts) {
  const tz = getTimezone();
  return tz ? { ...opts, timeZone: tz } : opts;
}

export function formatDate(value) {
  const d = parseUtc(value);
  if (!d || Number.isNaN(d.getTime())) return '-';
  return d.toLocaleString(undefined, withTimezone({
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }));
}

export function formatShortDate(value) {
  const d = parseUtc(value);
  if (!d || Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, withTimezone({ month: 'short', day: 'numeric' }));
}
