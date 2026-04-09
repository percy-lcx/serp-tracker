import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api/client';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

function formatDate(dateStr) {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString();
}

function formatShortDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function statusBadge(status) {
  const map = {
    completed: 'badge-success',
    failed: 'badge-danger',
    running: 'badge-info',
    pending: 'badge-neutral',
    aborted: 'badge-warning',
    success: 'badge-success',
    error: 'badge-danger',
  };
  return <span className={`badge ${map[status] || 'badge-neutral'}`}>{status}</span>;
}

export default function JobDetail() {
  const { id } = useParams();
  const [job, setJob] = useState(null);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedRow, setExpandedRow] = useState(null);
  const [lightboxUrl, setLightboxUrl] = useState(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.getJobs(),
      api.getJobResults(id, 200, 0),
    ])
      .then(([jobsData, resultsData]) => {
        const jobs = Array.isArray(jobsData) ? jobsData : jobsData.items || [];
        const found = jobs.find((j) => String(j.id) === String(id));
        setJob(found || null);
        const items = Array.isArray(resultsData) ? resultsData : resultsData.items || [];
        setResults(items);
        setError(null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  const toggleRow = useCallback((rowId) => {
    setExpandedRow((prev) => (prev === rowId ? null : rowId));
  }, []);

  const openLightbox = useCallback((url) => {
    setLightboxUrl(url);
  }, []);

  const closeLightbox = useCallback(() => {
    setLightboxUrl(null);
  }, []);

  if (loading) return <div className="empty-state">Loading job details...</div>;
  if (error) return <div className="card" style={{ color: 'var(--danger)' }}>Error: {error}</div>;
  if (!job) return <div className="empty-state">Job not found.</div>;

  // Prepare chart data sorted chronologically
  const chartData = results
    .filter((r) => r.position != null)
    .sort((a, b) => new Date(a.created_at || a.checked_at || 0) - new Date(b.created_at || b.checked_at || 0))
    .map((r) => ({
      date: formatShortDate(r.created_at || r.checked_at),
      position: r.position,
    }));

  // Compute y-axis domain for inverted axis
  const positions = chartData.map((d) => d.position);
  const minPos = positions.length > 0 ? Math.min(...positions) : 1;
  const maxPos = positions.length > 0 ? Math.max(...positions) : 100;
  const yMin = Math.max(1, minPos - 1);
  const yMax = maxPos + 2;

  // AIO timeline data
  const aioTimeline = results
    .sort((a, b) => new Date(a.created_at || a.checked_at || 0) - new Date(b.created_at || b.checked_at || 0))
    .map((r) => ({
      id: r.id,
      date: formatShortDate(r.created_at || r.checked_at),
      fullDate: formatDate(r.created_at || r.checked_at),
      aioPresent: r.aio_present,
      aioCited: r.aio_cited,
    }));

  return (
    <div>
      <div className="flex items-center gap-4 mb-4">
        <Link to="/jobs" className="btn btn-outline btn-sm">Back to Jobs</Link>
        <h1 className="page-title" style={{ marginBottom: 0 }}>Job Detail</h1>
      </div>

      {/* Job Info Card */}
      <div className="card">
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Job Information</h2>
        <div className="flex flex-wrap gap-4">
          <div style={{ minWidth: 200 }}>
            <span className="text-sm text-muted">Query</span>
            <div style={{ marginTop: 4, fontWeight: 600, fontSize: 16 }}>{job.query}</div>
          </div>
          <div style={{ minWidth: 200 }}>
            <span className="text-sm text-muted">Target URL</span>
            <div style={{ marginTop: 4, wordBreak: 'break-all' }}>{job.target_url || job.url || '-'}</div>
          </div>
          <div>
            <span className="text-sm text-muted">GL (Country)</span>
            <div style={{ marginTop: 4, fontWeight: 500 }}>{job.gl || '-'}</div>
          </div>
          <div>
            <span className="text-sm text-muted">HL (Language)</span>
            <div style={{ marginTop: 4, fontWeight: 500 }}>{job.hl || '-'}</div>
          </div>
          {job.status && (
            <div>
              <span className="text-sm text-muted">Status</span>
              <div style={{ marginTop: 4 }}>{statusBadge(job.status)}</div>
            </div>
          )}
        </div>
      </div>

      {/* Position Trend Chart */}
      {chartData.length > 1 && (
        <div className="chart-container">
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Position Trend</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
              />
              <YAxis
                reversed
                domain={[yMin, yMax]}
                tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
                label={{ value: 'Position', angle: -90, position: 'insideLeft', style: { fontSize: 12, fill: 'var(--text-muted)' } }}
              />
              <Tooltip
                contentStyle={{ fontSize: 13, borderRadius: 8, border: '1px solid var(--border)' }}
                formatter={(value) => [`Position ${value}`, 'Rank']}
              />
              <Line
                type="monotone"
                dataKey="position"
                stroke="var(--primary)"
                strokeWidth={2}
                dot={{ fill: 'var(--primary)', r: 4 }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* AIO Timeline */}
      {aioTimeline.length > 0 && aioTimeline.some((t) => t.aioPresent != null) && (
        <div className="card">
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>AIO Timeline</h2>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            {aioTimeline.map((entry, idx) => {
              let bgColor = 'var(--border)'; // No data / not present
              let title = `${entry.fullDate}: AIO not present`;
              if (entry.aioPresent && entry.aioCited) {
                bgColor = 'var(--success)';
                title = `${entry.fullDate}: AIO present, target cited`;
              } else if (entry.aioPresent) {
                bgColor = 'var(--warning)';
                title = `${entry.fullDate}: AIO present, target NOT cited`;
              }
              return (
                <div
                  key={entry.id || idx}
                  title={title}
                  style={{
                    width: 28,
                    height: 36,
                    borderRadius: 4,
                    backgroundColor: bgColor,
                    cursor: 'default',
                    display: 'flex',
                    alignItems: 'flex-end',
                    justifyContent: 'center',
                    paddingBottom: 2,
                  }}
                >
                  <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>{entry.date}</span>
                </div>
              );
            })}
          </div>
          <div className="flex gap-4 mt-4" style={{ fontSize: 12 }}>
            <div className="flex items-center gap-2">
              <span style={{ display: 'inline-block', width: 12, height: 12, borderRadius: 2, backgroundColor: 'var(--success)' }} />
              AIO Present + Cited
            </div>
            <div className="flex items-center gap-2">
              <span style={{ display: 'inline-block', width: 12, height: 12, borderRadius: 2, backgroundColor: 'var(--warning)' }} />
              AIO Present, Not Cited
            </div>
            <div className="flex items-center gap-2">
              <span style={{ display: 'inline-block', width: 12, height: 12, borderRadius: 2, backgroundColor: 'var(--border)' }} />
              No AIO
            </div>
          </div>
        </div>
      )}

      {/* Results History Table */}
      <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Results History</h2>

      {results.length === 0 ? (
        <div className="empty-state">No results recorded for this job yet.</div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: 30 }} />
                <th>Date</th>
                <th>Position</th>
                <th>AIO Present</th>
                <th>AIO Cited</th>
                <th>Status</th>
                <th>Screenshots</th>
              </tr>
            </thead>
            <tbody>
              {results
                .sort((a, b) => new Date(b.created_at || b.checked_at || 0) - new Date(a.created_at || a.checked_at || 0))
                .map((result, idx) => {
                  const rowId = result.id || idx;
                  const isExpanded = expandedRow === rowId;
                  const hasError = result.error || result.status === 'error' || result.status === 'failed';
                  return (
                    <ResultRow
                      key={rowId}
                      result={result}
                      rowId={rowId}
                      isExpanded={isExpanded}
                      hasError={hasError}
                      onToggle={toggleRow}
                      onScreenshotClick={openLightbox}
                    />
                  );
                })}
            </tbody>
          </table>
        </div>
      )}

      {/* Lightbox */}
      {lightboxUrl && (
        <div className="screenshot-viewer" onClick={closeLightbox}>
          <img src={lightboxUrl} alt="Screenshot" />
        </div>
      )}
    </div>
  );
}

function ResultRow({ result, rowId, isExpanded, hasError, onToggle, onScreenshotClick }) {
  const page1ScreenshotUrl = result.id ? api.getScreenshotUrl(result.id, 'page1') : null;
  const page2ScreenshotUrl = result.id ? api.getScreenshotUrl(result.id, 'page2') : null;
  const aioScreenshotUrl = result.id ? api.getScreenshotUrl(result.id, 'aio') : null;

  return (
    <>
      <tr
        style={{ cursor: 'pointer' }}
        onClick={() => onToggle(rowId)}
      >
        <td style={{ textAlign: 'center', fontSize: 16, color: 'var(--text-muted)' }}>
          {isExpanded ? '\u25BC' : '\u25B6'}
        </td>
        <td>{formatDate(result.created_at || result.checked_at)}</td>
        <td>
          {result.position != null ? (
            <div>
              <span style={{ fontWeight: 600 }}>{result.position}</span>
              {result.result_url && (
                <div style={{ fontSize: 11, color: 'var(--text-muted)', wordBreak: 'break-all', maxWidth: 250, lineHeight: 1.3, marginTop: 2 }}>
                  {result.result_url}
                </div>
              )}
            </div>
          ) : (
            <span className="text-muted">-</span>
          )}
        </td>
        <td>
          {result.aio_present != null ? (
            <span className={`badge ${result.aio_present ? 'badge-info' : 'badge-neutral'}`}>
              {result.aio_present ? 'Yes' : 'No'}
            </span>
          ) : (
            <span className="text-muted">-</span>
          )}
        </td>
        <td>
          {result.aio_cited != null ? (
            <span className={`badge ${result.aio_cited ? 'badge-success' : 'badge-neutral'}`}>
              {result.aio_cited ? 'Yes' : 'No'}
            </span>
          ) : (
            <span className="text-muted">-</span>
          )}
        </td>
        <td>
          {hasError ? (
            <span className="badge badge-danger">Error</span>
          ) : (
            <span className="badge badge-success">OK</span>
          )}
        </td>
        <td>
          {result.id ? (
            <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
              {page1ScreenshotUrl && (
                <img
                  src={page1ScreenshotUrl}
                  alt="Page 1"
                  onClick={() => onScreenshotClick(page1ScreenshotUrl)}
                  style={{
                    width: 48,
                    height: 32,
                    objectFit: 'cover',
                    borderRadius: 4,
                    border: '1px solid var(--border)',
                    cursor: 'pointer',
                  }}
                />
              )}
              {page2ScreenshotUrl && (
                <img
                  src={page2ScreenshotUrl}
                  alt="Page 2"
                  onClick={() => onScreenshotClick(page2ScreenshotUrl)}
                  style={{
                    width: 48,
                    height: 32,
                    objectFit: 'cover',
                    borderRadius: 4,
                    border: '1px solid var(--border)',
                    cursor: 'pointer',
                  }}
                />
              )}
              {aioScreenshotUrl && (
                <img
                  src={aioScreenshotUrl}
                  alt="AIO"
                  onClick={() => onScreenshotClick(aioScreenshotUrl)}
                  style={{
                    width: 48,
                    height: 32,
                    objectFit: 'cover',
                    borderRadius: 4,
                    border: '1px solid var(--border)',
                    cursor: 'pointer',
                  }}
                />
              )}
            </div>
          ) : (
            <span className="text-muted">-</span>
          )}
        </td>
      </tr>
      {isExpanded && (
        <tr>
          <td colSpan={7} style={{ background: '#f8fafc', padding: 16 }}>
            <div className="flex flex-wrap gap-4">
              <div>
                <span className="text-sm text-muted">Run ID</span>
                <div style={{ marginTop: 2 }}>
                  {result.run_id ? (
                    <Link to={`/history/${result.run_id}`} style={{ color: 'var(--primary)', textDecoration: 'none' }}>
                      #{result.run_id}
                    </Link>
                  ) : '-'}
                </div>
              </div>
              <div>
                <span className="text-sm text-muted">Position</span>
                <div style={{ marginTop: 2, fontWeight: 600 }}>{result.position ?? '-'}</div>
              </div>
              <div>
                <span className="text-sm text-muted">AIO Present</span>
                <div style={{ marginTop: 2 }}>{result.aio_present != null ? (result.aio_present ? 'Yes' : 'No') : '-'}</div>
              </div>
              <div>
                <span className="text-sm text-muted">AIO Cited</span>
                <div style={{ marginTop: 2 }}>{result.aio_cited != null ? (result.aio_cited ? 'Yes' : 'No') : '-'}</div>
              </div>
              {result.aio_position != null && (
                <div>
                  <span className="text-sm text-muted">AIO Position</span>
                  <div style={{ marginTop: 2 }}>{result.aio_position}</div>
                </div>
              )}
              {result.serp_features && (
                <div>
                  <span className="text-sm text-muted">SERP Features</span>
                  <div style={{ marginTop: 2 }}>
                    {Array.isArray(result.serp_features)
                      ? result.serp_features.join(', ')
                      : String(result.serp_features)}
                  </div>
                </div>
              )}
              {result.error && (
                <div style={{ flexBasis: '100%' }}>
                  <span className="text-sm text-muted">Error Details</span>
                  <div style={{ marginTop: 2, color: 'var(--danger)', fontFamily: 'monospace', fontSize: 12 }}>
                    {result.error}
                  </div>
                </div>
              )}
              {result.organic_results && result.organic_results.length > 0 && (
                <div style={{ flexBasis: '100%' }}>
                  <span className="text-sm text-muted">Organic Results ({result.organic_results.length})</span>
                  <div style={{ marginTop: 4, fontSize: 12, lineHeight: 1.6 }}>
                    {result.organic_results
                      .sort((a, b) => a.position - b.position)
                      .map((org) => (
                        <div
                          key={org.id}
                          style={{
                            display: 'flex',
                            gap: 8,
                            alignItems: 'baseline',
                            padding: '2px 0',
                            background: org.is_target ? 'rgba(34,197,94,0.1)' : 'transparent',
                            borderRadius: 4,
                            paddingLeft: 4,
                          }}
                        >
                          <span style={{ fontWeight: 600, minWidth: 24, color: 'var(--text-muted)' }}>
                            {org.position}.
                          </span>
                          <a
                            href={org.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              color: org.is_target ? 'var(--success)' : 'var(--primary)',
                              wordBreak: 'break-all',
                              fontWeight: org.is_target ? 600 : 400,
                            }}
                          >
                            {org.url}
                          </a>
                          {org.is_target && (
                            <span className="badge badge-success" style={{ fontSize: 10 }}>target</span>
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              )}
              {result.aio_citations && result.aio_citations.length > 0 && (
                <div style={{ flexBasis: '100%' }}>
                  <span className="text-sm text-muted">AIO Citations ({result.aio_citations.length})</span>
                  <div style={{ marginTop: 4, fontSize: 12, lineHeight: 1.6 }}>
                    {result.aio_citations
                      .sort((a, b) => a.position - b.position)
                      .map((cit) => (
                        <div
                          key={cit.id}
                          style={{
                            display: 'flex',
                            gap: 8,
                            alignItems: 'baseline',
                            padding: '2px 0',
                            background: cit.is_target ? 'rgba(34,197,94,0.1)' : 'transparent',
                            borderRadius: 4,
                            paddingLeft: 4,
                          }}
                        >
                          <span style={{ fontWeight: 600, minWidth: 24, color: 'var(--text-muted)' }}>
                            {cit.position}.
                          </span>
                          <a
                            href={cit.cited_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              color: cit.is_target ? 'var(--success)' : 'var(--primary)',
                              wordBreak: 'break-all',
                              fontWeight: cit.is_target ? 600 : 400,
                            }}
                          >
                            {cit.cited_url}
                          </a>
                          {cit.is_target && (
                            <span className="badge badge-success" style={{ fontSize: 10 }}>target</span>
                          )}
                          {cit.citation_type && cit.citation_type !== 'inline' && (
                            <span className="badge" style={{ fontSize: 10, background: 'rgba(59,130,246,0.15)', color: 'var(--primary)' }}>
                              {cit.citation_type}
                            </span>
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              )}
              {result.debug_log && (
                <div style={{ flexBasis: '100%' }}>
                  <span className="text-sm text-muted">Debug Log</span>
                  <pre style={{
                    marginTop: 4,
                    padding: '0.5rem',
                    background: '#1a1a2e',
                    color: '#e0e0e0',
                    borderRadius: 4,
                    fontSize: 11,
                    lineHeight: 1.5,
                    overflow: 'auto',
                    maxHeight: 300,
                    whiteSpace: 'pre-wrap',
                  }}>
                    {result.debug_log}
                  </pre>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
