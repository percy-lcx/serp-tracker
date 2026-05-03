import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { formatDate } from '../utils/date';
import { getOffsetLabel, listTimezones, setTimezone, useTimezone } from '../utils/timezone';

export default function Settings() {
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [savingDomain, setSavingDomain] = useState(null);
  const tz = useTimezone();
  const allZones = useMemo(() => listTimezones(), []);
  // Pre-compute "(UTC+N)" labels once — Intl.DateTimeFormat per zone is non-trivial
  // and there are ~400 zones. Sort by offset (most negative first), then by name.
  const zoneOptions = useMemo(() => {
    const parseOffset = (s) => {
      const m = /^UTC([+-])(\d+)(?::(\d+))?$/.exec(s || '');
      if (!m) return 0;
      return (m[1] === '-' ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3] || 0));
    };
    return allZones
      .map((z) => {
        const off = getOffsetLabel(z);
        return { zone: z, label: `(${off}) ${z}`, offset: parseOffset(off) };
      })
      .sort((a, b) => a.offset - b.offset || a.zone.localeCompare(b.zone));
  }, [allZones]);
  const browserZone = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'local';
    } catch {
      return 'local';
    }
  }, []);
  const browserZoneLabel = useMemo(() => {
    const off = getOffsetLabel(browserZone);
    return off ? `${browserZone}, ${off}` : browserZone;
  }, [browserZone]);
  // tz is read via getTimezone() inside formatDate; referenced here so the
  // preview re-renders when the dropdown changes.
  void tz;
  const previewNow = formatDate(new Date().toISOString());

  const fetchProfiles = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getProfiles();
      setProfiles(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProfiles();
  }, [fetchProfiles]);

  const toggleSubdomains = useCallback(async (profile) => {
    setSavingDomain(profile.domain);
    try {
      const updated = await api.updateProfile(profile.domain, {
        include_subdomains: !profile.include_subdomains,
      });
      setProfiles((prev) => prev.map((p) => (p.domain === updated.domain ? updated : p)));
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingDomain(null);
    }
  }, []);

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h1 className="page-title">Settings</h1>
      </div>

      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>Display timezone</h2>
        <p className="text-muted" style={{ fontSize: 13, marginBottom: 12, maxWidth: 640 }}>
          All timestamps in the UI are rendered in this timezone. Backend storage stays UTC.
        </p>
        <div className="flex items-center gap-4" style={{ flexWrap: 'wrap' }}>
          <select
            value={tz}
            onChange={(e) => setTimezone(e.target.value)}
            style={{ padding: '6px 10px', minWidth: 280 }}
          >
            <option value="">Browser default ({browserZoneLabel})</option>
            <option value="UTC">UTC (UTC+0)</option>
            <optgroup label="All timezones">
              {zoneOptions.map(({ zone, label }) => (
                <option key={zone} value={zone}>{label}</option>
              ))}
            </optgroup>
          </select>
          <span className="text-muted" style={{ fontSize: 13 }}>
            Now: <strong style={{ color: 'var(--text)' }}>{previewNow}</strong>
          </span>
        </div>
      </section>

      <section>
        <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>Site profiles</h2>
        <p className="text-muted" style={{ fontSize: 13, marginBottom: 16, maxWidth: 640 }}>
          A profile is created automatically for every domain you track. When{' '}
          <strong>Include subdomains</strong> is on, any host on the registered domain
          (e.g. <code>de.example.com</code>) counts as a same-domain hit alongside the
          tracked URL. Turn it off if subdomains on this site represent different
          properties.
        </p>

        {error && (
          <div className="card mb-4" style={{ borderColor: 'var(--danger)', color: 'var(--danger)' }}>
            {error}
          </div>
        )}

        {loading ? (
          <div className="empty-state">Loading…</div>
        ) : profiles.length === 0 ? (
          <div className="empty-state">
            No profiles yet. Create a tracking job to add one.
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Domain</th>
                <th>Include subdomains</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((p) => (
                <tr key={p.domain}>
                  <td><code>{p.domain}</code></td>
                  <td>
                    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                      <input
                        type="checkbox"
                        checked={p.include_subdomains}
                        disabled={savingDomain === p.domain}
                        onChange={() => toggleSubdomains(p)}
                      />
                      <span className={`badge ${p.include_subdomains ? 'badge-success' : 'badge-neutral'}`}>
                        {p.include_subdomains ? 'On' : 'Off'}
                      </span>
                    </label>
                  </td>
                  <td className="text-muted" style={{ fontSize: 12 }}>
                    {formatDate(p.updated_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
