import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api/client';

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

function formatDate(dateStr) {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString();
}

function progressPercent(run) {
  const total = run.total_jobs ?? run.total ?? 0;
  const done = (run.completed_jobs ?? run.completed ?? 0) + (run.failed_jobs ?? run.failed ?? 0);
  if (total === 0) return 0;
  return Math.round((done / total) * 100);
}

export default function RunDetail() {
  const { id } = useParams();
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    api.getRun(id)
      .then((data) => {
        setRun(data);
        setError(null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="empty-state">Loading run details...</div>;
  if (error) return <div className="card" style={{ color: 'var(--danger)' }}>Error: {error}</div>;
  if (!run) return <div className="empty-state">Run not found.</div>;

  const pct = progressPercent(run);
  const results = run.results || run.jobs || [];

  return (
    <div>
      <div className="flex items-center gap-4 mb-4">
        <Link to="/history" className="btn btn-outline btn-sm">Back to History</Link>
        <h1 className="page-title" style={{ marginBottom: 0 }}>Run #{run.id}</h1>
      </div>

      <div className="card">
        <div className="flex flex-wrap gap-4" style={{ marginBottom: 16 }}>
          <div>
            <span className="text-sm text-muted">Status</span>
            <div style={{ marginTop: 4 }}>{statusBadge(run.status)}</div>
          </div>
          <div>
            <span className="text-sm text-muted">Started</span>
            <div style={{ marginTop: 4, fontWeight: 500 }}>{formatDate(run.started_at || run.created_at)}</div>
          </div>
          <div>
            <span className="text-sm text-muted">Ended</span>
            <div style={{ marginTop: 4, fontWeight: 500 }}>{formatDate(run.finished_at || run.ended_at)}</div>
          </div>
          <div>
            <span className="text-sm text-muted">Progress</span>
            <div style={{ marginTop: 4, fontWeight: 500 }}>
              {run.completed_jobs ?? run.completed ?? 0} / {run.total_jobs ?? run.total ?? 0} jobs
            </div>
          </div>
        </div>
        <div className="progress-bar">
          <div className="fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="text-sm text-muted" style={{ marginTop: 4 }}>{pct}% complete</div>
      </div>

      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12 }}>Job Results</h2>

      {results.length === 0 ? (
        <div className="empty-state">No results available for this run.</div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table>
            <thead>
              <tr>
                <th>Query</th>
                <th>Position</th>
                <th>AIO Present</th>
                <th>AIO Cited</th>
                <th>Error</th>
                <th>Screenshots</th>
              </tr>
            </thead>
            <tbody>
              {results.map((result, idx) => {
                const query = result.query || result.job?.query || '-';
                const hasError = result.error || result.status === 'error' || result.status === 'failed';
                return (
                  <tr key={result.id || idx}>
                    <td>
                      {result.job_id ? (
                        <Link to={`/jobs/${result.job_id}`} style={{ color: 'var(--primary)', textDecoration: 'none' }}>
                          {query}
                        </Link>
                      ) : (
                        query
                      )}
                    </td>
                    <td>
                      {result.position != null ? (
                        <span style={{ fontWeight: 600 }}>{result.position}</span>
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
                        <span className="badge badge-danger" title={result.error || ''}>
                          {result.error ? result.error.substring(0, 40) : 'Error'}
                        </span>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                    <td>
                      {result.id ? (
                        <div className="flex gap-2">
                          <a
                            href={api.getScreenshotUrl(result.id, 'page1')}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="btn btn-outline btn-sm"
                          >
                            Full
                          </a>
                          <a
                            href={api.getScreenshotUrl(result.id, 'aio')}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="btn btn-outline btn-sm"
                          >
                            AIO
                          </a>
                        </div>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
