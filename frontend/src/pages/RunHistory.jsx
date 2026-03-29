import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

function statusBadge(status) {
  const map = {
    completed: 'badge-success',
    failed: 'badge-danger',
    running: 'badge-info',
    pending: 'badge-neutral',
    aborted: 'badge-warning',
  };
  return <span className={`badge ${map[status] || 'badge-neutral'}`}>{status}</span>;
}

function formatDuration(start, end) {
  if (!start) return '-';
  const s = new Date(start);
  const e = end ? new Date(end) : new Date();
  const diff = Math.floor((e - s) / 1000);
  if (diff < 60) return `${diff}s`;
  const mins = Math.floor(diff / 60);
  const secs = diff % 60;
  if (mins < 60) return `${mins}m ${secs}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

function formatDate(dateStr) {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString();
}

export default function RunHistory() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [offset, setOffset] = useState(0);
  const limit = 20;

  useEffect(() => {
    setLoading(true);
    api.getRuns(limit, offset)
      .then((data) => {
        setRuns(Array.isArray(data) ? data : data.items || []);
        setError(null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [offset]);

  return (
    <div>
      <h1 className="page-title">Run History</h1>

      {error && (
        <div className="card" style={{ color: 'var(--danger)' }}>
          Error loading runs: {error}
        </div>
      )}

      {loading ? (
        <div className="empty-state">Loading runs...</div>
      ) : runs.length === 0 ? (
        <div className="empty-state">
          <p>No runs found.</p>
          <p className="text-sm text-muted mt-4">
            Start a new run from the <Link to="/run">Run Control</Link> page.
          </p>
        </div>
      ) : (
        <>
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Total Jobs</th>
                  <th>Completed</th>
                  <th>Failed</th>
                  <th>Duration</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <Link to={`/history/${run.id}`} style={{ color: 'var(--primary)', textDecoration: 'none', fontWeight: 500 }}>
                        {formatDate(run.started_at || run.created_at)}
                      </Link>
                    </td>
                    <td>{statusBadge(run.status)}</td>
                    <td>{run.total_jobs ?? run.total ?? '-'}</td>
                    <td>{run.completed_jobs ?? run.completed ?? '-'}</td>
                    <td>{run.failed_jobs ?? run.failed ?? '-'}</td>
                    <td>{formatDuration(run.started_at || run.created_at, run.finished_at || run.ended_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between mt-4">
            <button
              className="btn btn-outline btn-sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              Previous
            </button>
            <span className="text-sm text-muted">
              Showing {offset + 1} - {offset + runs.length}
            </span>
            <button
              className="btn btn-outline btn-sm"
              disabled={runs.length < limit}
              onClick={() => setOffset(offset + limit)}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
