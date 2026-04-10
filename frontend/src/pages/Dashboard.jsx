import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

function Dashboard() {
  const [stats, setStats] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [filterGl, setFilterGl] = useState('');
  const [filterHl, setFilterHl] = useState('');
  const [filterAio, setFilterAio] = useState('');
  const [filterPosMin, setFilterPosMin] = useState('');
  const [filterPosMax, setFilterPosMax] = useState('');

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const [statsData, jobsData] = await Promise.all([
          api.getStats(),
          api.getJobs(),
        ]);
        setStats(statsData);
        setJobs(jobsData || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const glOptions = [...new Set(jobs.map((j) => j.gl).filter(Boolean))].sort();
  const hlOptions = [...new Set(jobs.map((j) => j.hl).filter(Boolean))].sort();

  const filteredJobs = jobs.filter((job) => {
    if (filterGl && job.gl !== filterGl) return false;
    if (filterHl && job.hl !== filterHl) return false;
    if (filterAio === 'present' && !job.aio_status) return false;
    if (filterAio === 'absent' && job.aio_status) return false;
    if (filterPosMin !== '' && (job.position == null || job.position < Number(filterPosMin))) return false;
    if (filterPosMax !== '' && (job.position == null || job.position > Number(filterPosMax))) return false;
    return true;
  });

  function formatDate(dateStr) {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleDateString();
  }

  function renderPositionChange(job) {
    const pos = job.position;
    const prev = job.previous_position;

    if (pos == null) return <span className="text-muted">—</span>;

    if (prev == null || prev === pos) {
      return <span className="position-same">{pos}</span>;
    }

    if (pos < prev) {
      return (
        <span className="position-up">
          {pos} ▲ <span className="text-sm">({prev - pos})</span>
        </span>
      );
    }

    return (
      <span className="position-down">
        {pos} ▼ <span className="text-sm">({pos - prev})</span>
      </span>
    );
  }

  function renderAioBadge(status) {
    if (!status) return <span className="badge badge-neutral">None</span>;
    if (status === 'present' || status === 'cited') {
      return <span className="badge badge-success">{status}</span>;
    }
    if (status === 'absent') {
      return <span className="badge badge-danger">{status}</span>;
    }
    return <span className="badge badge-info">{status}</span>;
  }

  function clearFilters() {
    setFilterGl('');
    setFilterHl('');
    setFilterAio('');
    setFilterPosMin('');
    setFilterPosMax('');
  }

  const hasFilters = filterGl || filterHl || filterAio || filterPosMin !== '' || filterPosMax !== '';

  if (loading) {
    return (
      <div>
        <h1 className="page-title">Dashboard</h1>
        <p className="text-muted">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <h1 className="page-title">Dashboard</h1>
        <div className="card">
          <p style={{ color: 'var(--danger)' }}>Error: {error}</p>
        </div>
      </div>
    );
  }

  const activeJobs = jobs.filter((j) => j.active !== false).length;

  return (
    <div>
      <h1 className="page-title">Dashboard</h1>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="label">Active Jobs</div>
          <div className="value">{activeJobs}</div>
        </div>
        <div className="stat-card">
          <div className="label">Total Jobs</div>
          <div className="value">{jobs.length}</div>
        </div>
        <div className="stat-card">
          <div className="label">Last Run</div>
          <div className="value" style={{ fontSize: 18 }}>
            {stats?.last_run_date ? formatDate(stats.last_run_date) : '—'}
          </div>
        </div>
        <div className="stat-card">
          <div className="label">Last Run Status</div>
          <div className="value" style={{ fontSize: 18 }}>
            {stats?.last_run_status ? (
              <span
                className={
                  stats.last_run_status === 'completed'
                    ? 'badge badge-success'
                    : stats.last_run_status === 'failed'
                    ? 'badge badge-danger'
                    : 'badge badge-warning'
                }
              >
                {stats.last_run_status}
              </span>
            ) : (
              '—'
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 style={{ fontSize: 16, fontWeight: 600 }}>All Jobs</h2>
          {hasFilters && (
            <button className="btn btn-outline btn-sm" onClick={clearFilters}>
              Clear Filters
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          <div className="form-group" style={{ marginBottom: 0, minWidth: 120 }}>
            <label>GL (Country)</label>
            <select value={filterGl} onChange={(e) => setFilterGl(e.target.value)}>
              <option value="">All</option>
              {glOptions.map((gl) => (
                <option key={gl} value={gl}>{gl}</option>
              ))}
            </select>
          </div>

          <div className="form-group" style={{ marginBottom: 0, minWidth: 120 }}>
            <label>HL (Language)</label>
            <select value={filterHl} onChange={(e) => setFilterHl(e.target.value)}>
              <option value="">All</option>
              {hlOptions.map((hl) => (
                <option key={hl} value={hl}>{hl}</option>
              ))}
            </select>
          </div>

          <div className="form-group" style={{ marginBottom: 0, minWidth: 120 }}>
            <label>AIO Presence</label>
            <select value={filterAio} onChange={(e) => setFilterAio(e.target.value)}>
              <option value="">All</option>
              <option value="present">Present</option>
              <option value="absent">Absent</option>
            </select>
          </div>

          <div className="form-group" style={{ marginBottom: 0, minWidth: 80 }}>
            <label>Pos Min</label>
            <input
              type="number"
              min="1"
              placeholder="1"
              value={filterPosMin}
              onChange={(e) => setFilterPosMin(e.target.value)}
            />
          </div>

          <div className="form-group" style={{ marginBottom: 0, minWidth: 80 }}>
            <label>Pos Max</label>
            <input
              type="number"
              min="1"
              placeholder="100"
              value={filterPosMax}
              onChange={(e) => setFilterPosMax(e.target.value)}
            />
          </div>
        </div>

        {filteredJobs.length === 0 ? (
          <div className="empty-state">
            <p>No jobs match the current filters.</p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Query</th>
                <th>Target URL</th>
                <th>GL / HL</th>
                <th>Position</th>
                <th>AIO Status</th>
                <th>Last Checked</th>
              </tr>
            </thead>
            <tbody>
              {filteredJobs.map((job) => (
                <tr key={job.id}>
                  <td>
                    <Link to={`/jobs/${job.id}`} style={{ color: 'var(--primary)', textDecoration: 'none', fontWeight: 500 }}>
                      {job.query}
                    </Link>
                  </td>
                  <td className="text-sm text-muted" style={{ maxWidth: 250, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {job.target_url}
                  </td>
                  <td>{job.gl || '—'} / {job.hl || '—'}</td>
                  <td>
                    <div>
                      {renderPositionChange(job)}
                      {job.latest_result_title && (
                        <div style={{ fontSize: 11, color: 'var(--text)', wordBreak: 'break-all', maxWidth: 220, lineHeight: 1.3, marginTop: 2 }}>
                          {job.latest_result_title}
                        </div>
                      )}
                      {job.latest_result_url && (
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', wordBreak: 'break-all', maxWidth: 220, lineHeight: 1.3, marginTop: 2 }}>
                          {job.latest_result_url}
                        </div>
                      )}
                    </div>
                  </td>
                  <td>
                    <div>
                      {renderAioBadge(job.aio_status)}
                      {job.latest_aio_citation_url && (
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', wordBreak: 'break-all', maxWidth: 220, lineHeight: 1.3, marginTop: 2 }}>
                          {job.latest_aio_citation_url}
                        </div>
                      )}
                    </div>
                  </td>
                  <td>{formatDate(job.last_checked)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="flex justify-between items-center mt-4">
          <span className="text-sm text-muted">
            Showing {filteredJobs.length} of {jobs.length} jobs
          </span>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
