import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../api/client';
import { useRunWebSocket } from '../hooks/useWebSocket';

function formatElapsed(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function getJobStatus(messages, jobId) {
  let current = 'queued';
  for (const msg of messages) {
    if (msg.job_id !== jobId) continue;
    if (msg.type === 'job_started') current = 'running';
    else if (msg.type === 'job_completed') current = 'done';
    else if (msg.type === 'job_error') current = 'error';
  }
  return current;
}

function StatusBadge({ status }) {
  if (!status) return null;
  const classMap = {
    running: 'badge-info',
    paused_captcha: 'badge-warning',
    completed: 'badge-success',
    aborted: 'badge-danger',
  };
  const labelMap = {
    running: 'Running',
    paused_captcha: 'Paused — CAPTCHA',
    completed: 'Completed',
    aborted: 'Aborted',
  };
  return (
    <span className={`badge ${classMap[status] || 'badge-secondary'}`}>
      {labelMap[status] || status}
    </span>
  );
}

export default function RunControl() {
  const [jobs, setJobs] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [runId, setRunId] = useState(null);
  const [triggering, setTriggering] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  const timerRef = useRef(null);
  const { messages, progress, status, reset } = useRunWebSocket(runId);

  // Load jobs on mount
  useEffect(() => {
    let cancelled = false;
    api
      .getJobs()
      .then((data) => {
        if (!cancelled) setJobs(Array.isArray(data) ? data : data.items || []);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Elapsed timer while running
  useEffect(() => {
    if (status === 'running' || status === 'paused_captcha') {
      timerRef.current = setInterval(() => {
        setElapsed((prev) => prev + 1);
      }, 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [status]);

  const handleToggle = useCallback((id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleSelectAll = useCallback(() => {
    setSelected((prev) => {
      if (prev.size === jobs.length) return new Set();
      return new Set(jobs.map((j) => j.id));
    });
  }, [jobs]);

  const startRun = useCallback(
    async (payload) => {
      setTriggering(true);
      setError(null);
      try {
        reset();
        setElapsed(0);
        const result = await api.triggerRun(payload);
        setRunId(result.id);
      } catch (err) {
        setError(err.message);
      } finally {
        setTriggering(false);
      }
    },
    [reset],
  );

  const handleRunAll = useCallback(() => {
    startRun({ all_active: true });
  }, [startRun]);

  const handleRunSelected = useCallback(() => {
    if (selected.size === 0) return;
    startRun({ job_ids: Array.from(selected) });
  }, [selected, startRun]);

  const handleAbort = useCallback(async () => {
    if (!runId) return;
    try {
      await api.abortRun(runId);
    } catch (err) {
      setError(err.message);
    }
  }, [runId]);

  const isRunActive = status === 'running' || status === 'paused_captcha';
  const isFinished = status === 'completed' || status === 'aborted';

  const completedCount = progress ? progress.completed : 0;
  const totalCount = progress ? progress.total : 0;
  const progressPct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  // Derive per-job statuses from WS messages
  const trackedJobIds = progress?.job_ids || [];
  const jobStatusList = trackedJobIds.map((jid) => {
    const job = jobs.find((j) => j.id === jid);
    return {
      id: jid,
      label: job ? `${job.domain} — "${job.keyword}"` : `Job ${jid}`,
      status: getJobStatus(messages, jid),
    };
  });

  return (
    <div className="run-control">
      <h1>Run Control</h1>

      {error && (
        <div className="card" style={{ borderColor: '#e74c3c', background: '#fdf0ef' }}>
          <p style={{ color: '#c0392b', margin: 0 }}>{error}</p>
        </div>
      )}

      {/* Action buttons */}
      <div className="card">
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            className="btn-primary"
            onClick={handleRunAll}
            disabled={triggering || isRunActive}
          >
            {triggering ? 'Starting\u2026' : 'Run All Active Jobs'}
          </button>
          <button
            className="btn-secondary"
            onClick={handleRunSelected}
            disabled={triggering || isRunActive || selected.size === 0}
          >
            Run Selected ({selected.size})
          </button>
        </div>
      </div>

      {/* Jobs table */}
      <div className="card">
        <h2>Jobs</h2>
        {loading && <p>Loading jobs...</p>}
        {!loading && jobs.length === 0 && <p>No jobs found.</p>}
        {!loading && jobs.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>
                  <input
                    type="checkbox"
                    checked={selected.size === jobs.length && jobs.length > 0}
                    onChange={handleSelectAll}
                  />
                </th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Domain</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Keyword</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Engine</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Active</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} style={{ borderTop: '1px solid #eee' }}>
                  <td style={{ padding: '0.5rem' }}>
                    <input
                      type="checkbox"
                      checked={selected.has(job.id)}
                      onChange={() => handleToggle(job.id)}
                    />
                  </td>
                  <td style={{ padding: '0.5rem' }}>{job.domain}</td>
                  <td style={{ padding: '0.5rem' }}>{job.keyword}</td>
                  <td style={{ padding: '0.5rem' }}>{job.engine || 'google'}</td>
                  <td style={{ padding: '0.5rem' }}>
                    <span className={job.is_active ? 'badge-success' : 'badge-secondary'}>
                      {job.is_active ? 'Yes' : 'No'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Live status panel — shown when a run has been triggered */}
      {runId && (
        <div className="card">
          <h2>
            Run Status{' '}
            <StatusBadge status={status} />
          </h2>

          {/* CAPTCHA alert */}
          {status === 'paused_captcha' && (
            <div className="captcha-banner">
              CAPTCHA detected &mdash; please solve it in the browser window
            </div>
          )}

          {/* Progress bar */}
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
              <span>{completedCount} of {totalCount} jobs completed</span>
              <span>{progressPct}%</span>
            </div>
            <div className="progress-bar">
              <div
                className="fill"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          {/* Elapsed time */}
          <p>
            Elapsed time: <strong>{formatElapsed(elapsed)}</strong>
          </p>

          {/* Abort button */}
          {isRunActive && (
            <button className="btn-danger" onClick={handleAbort}>
              Abort Run
            </button>
          )}

          {isFinished && (
            <p style={{ fontStyle: 'italic' }}>
              Run {status === 'completed' ? 'completed successfully' : 'was aborted'} in{' '}
              {formatElapsed(elapsed)}.
            </p>
          )}

          {/* Per-job status list */}
          {jobStatusList.length > 0 && (
            <div style={{ marginTop: '1rem' }}>
              <h3>Per-Job Status</h3>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {jobStatusList.map((entry) => {
                  const statusClass = {
                    queued: 'badge-secondary',
                    running: 'badge-info',
                    done: 'badge-success',
                    error: 'badge-danger',
                  }[entry.status];
                  return (
                    <li
                      key={entry.id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        padding: '0.4rem 0',
                        borderBottom: '1px solid #eee',
                      }}
                    >
                      <span>{entry.label}</span>
                      <span className={`badge ${statusClass}`}>{entry.status}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
