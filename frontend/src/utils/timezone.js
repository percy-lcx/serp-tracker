// Display timezone preference, persisted in localStorage and shared across pages.
// Empty string means "use the browser's local timezone" (the JS default).

const KEY = 'serp-tracker:timezone';
const EVENT = 'serp-tracker:timezone-change';

export function getTimezone() {
  try {
    return window.localStorage.getItem(KEY) || '';
  } catch {
    return '';
  }
}

export function setTimezone(tz) {
  try {
    if (tz) window.localStorage.setItem(KEY, tz);
    else window.localStorage.removeItem(KEY);
  } catch {
    // localStorage unavailable (private mode, sandbox) — ignore.
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: tz || '' }));
}

export function listTimezones() {
  if (typeof Intl.supportedValuesOf === 'function') {
    return Intl.supportedValuesOf('timeZone');
  }
  // Older runtimes — minimal fallback covering common zones.
  return [
    'UTC',
    'America/Los_Angeles', 'America/Denver', 'America/Chicago', 'America/New_York',
    'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Moscow',
    'Asia/Dubai', 'Asia/Kolkata', 'Asia/Bangkok', 'Asia/Singapore', 'Asia/Hong_Kong',
    'Asia/Shanghai', 'Asia/Tokyo', 'Australia/Sydney', 'Pacific/Auckland',
  ];
}

// "UTC+8", "UTC-5:30", "UTC+0" for the current moment (DST-aware).
export function getOffsetLabel(tz) {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      timeZoneName: 'shortOffset',
    }).formatToParts(new Date());
    const tzPart = parts.find((p) => p.type === 'timeZoneName');
    if (tzPart && tzPart.value) {
      const v = tzPart.value.replace(/^GMT/, 'UTC');
      return v === 'UTC' ? 'UTC+0' : v;
    }
  } catch {
    // Some runtimes don't support 'shortOffset' — fall through to manual calc.
  }
  // Fallback: compute offset from the difference between the zone's wall time
  // and UTC at the same instant.
  try {
    const now = new Date();
    const fmt = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      hour12: false,
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
    const parts = Object.fromEntries(
      fmt.formatToParts(now).filter((p) => p.type !== 'literal').map((p) => [p.type, p.value])
    );
    const asLocal = Date.UTC(
      Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      Number(parts.hour) % 24, Number(parts.minute), Number(parts.second),
    );
    const offsetMin = Math.round((asLocal - now.getTime()) / 60000);
    const sign = offsetMin >= 0 ? '+' : '-';
    const abs = Math.abs(offsetMin);
    const hh = Math.floor(abs / 60);
    const mm = abs % 60;
    return `UTC${sign}${hh}${mm ? ':' + String(mm).padStart(2, '0') : ''}`;
  } catch {
    return '';
  }
}

// React hook so pages re-render when the timezone changes from anywhere.
import { useEffect, useState } from 'react';

export function useTimezone() {
  const [tz, setTz] = useState(getTimezone());
  useEffect(() => {
    const handler = (e) => setTz(e.detail || '');
    const storageHandler = (e) => {
      if (e.key === KEY) setTz(e.newValue || '');
    };
    window.addEventListener(EVENT, handler);
    window.addEventListener('storage', storageHandler);
    return () => {
      window.removeEventListener(EVENT, handler);
      window.removeEventListener('storage', storageHandler);
    };
  }, []);
  return tz;
}
