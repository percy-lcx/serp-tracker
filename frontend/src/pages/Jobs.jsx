import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

const EMPTY_FORM = { target_url: '', query: '', gl: 'us', hl: 'en' };

export default function Jobs() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingJob, setEditingJob] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  // Bulk selection
  const [selected, setSelected] = useState(new Set());

  // CSV import
  const [importing, setImporting] = useState(false);

  const fetchJobs = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getJobs();
      setJobs(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // ---------- Modal helpers ----------

  const openAdd = useCallback(() => {
    setEditingJob(null);
    setForm(EMPTY_FORM);
    setModalOpen(true);
  }, []);

  const openEdit = useCallback((job) => {
    setEditingJob(job);
    setForm({
      target_url: job.target_url || '',
      query: job.query || '',
      gl: job.gl || 'us',
      hl: job.hl || 'en',
    });
    setModalOpen(true);
  }, []);

  const closeModal = useCallback(() => {
    setModalOpen(false);
    setEditingJob(null);
    setForm(EMPTY_FORM);
  }, []);

  const handleChange = useCallback((e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }, []);

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editingJob) {
        await api.updateJob(editingJob.id, form);
      } else {
        await api.createJob(form);
      }
      closeModal();
      await fetchJobs();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }, [editingJob, form, closeModal, fetchJobs]);

  // ---------- Delete ----------

  const handleDelete = useCallback(async (job) => {
    if (!window.confirm(`Delete job "${job.query}"? This cannot be undone.`)) return;
    try {
      await api.deleteJob(job.id);
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(job.id);
        return next;
      });
      await fetchJobs();
    } catch (err) {
      setError(err.message);
    }
  }, [fetchJobs]);

  // ---------- Toggle active ----------

  const toggleActive = useCallback(async (job) => {
    try {
      await api.updateJob(job.id, { active: !job.active });
      await fetchJobs();
    } catch (err) {
      setError(err.message);
    }
  }, [fetchJobs]);

  // ---------- CSV import ----------

  const handleImport = useCallback(async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      await api.importJobs(file);
      await fetchJobs();
    } catch (err) {
      setError(err.message);
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  }, [fetchJobs]);

  // ---------- Bulk selection ----------

  const toggleSelect = useCallback((id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelected((prev) => {
      if (prev.size === jobs.length) return new Set();
      return new Set(jobs.map((j) => j.id));
    });
  }, [jobs]);

  // ---------- Bulk actions ----------

  const bulkSetActive = useCallback(async (active) => {
    try {
      await Promise.all(
        [...selected].map((id) => api.updateJob(id, { active }))
      );
      setSelected(new Set());
      await fetchJobs();
    } catch (err) {
      setError(err.message);
    }
  }, [selected, fetchJobs]);

  const bulkDelete = useCallback(async () => {
    if (!window.confirm(`Delete ${selected.size} selected job(s)? This cannot be undone.`)) return;
    try {
      await Promise.all([...selected].map((id) => api.deleteJob(id)));
      setSelected(new Set());
      await fetchJobs();
    } catch (err) {
      setError(err.message);
    }
  }, [selected, fetchJobs]);

  // ---------- Render ----------

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h1 className="page-title">Jobs</h1>
        <div className="flex gap-2">
          <label className="btn btn-outline" style={{ position: 'relative' }}>
            {importing ? 'Importing...' : 'Import CSV'}
            <input
              type="file"
              accept=".csv"
              onChange={handleImport}
              disabled={importing}
              style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer' }}
            />
          </label>
          <button className="btn btn-primary" onClick={openAdd}>
            + Add Job
          </button>
        </div>
      </div>

      {error && (
        <div className="card" style={{ borderColor: 'var(--danger)', color: 'var(--danger)' }}>
          {error}
          <button
            className="btn btn-sm btn-outline"
            style={{ marginLeft: 12 }}
            onClick={() => setError(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Bulk actions bar */}
      {selected.size > 0 && (
        <div className="card flex items-center gap-2">
          <span className="text-sm text-muted">{selected.size} selected</span>
          <button className="btn btn-sm btn-success" onClick={() => bulkSetActive(true)}>
            Activate
          </button>
          <button className="btn btn-sm btn-outline" onClick={() => bulkSetActive(false)}>
            Deactivate
          </button>
          <button className="btn btn-sm btn-danger" onClick={bulkDelete}>
            Delete
          </button>
        </div>
      )}

      <div className="card" style={{ padding: 0 }}>
        {loading ? (
          <div className="empty-state">Loading jobs...</div>
        ) : jobs.length === 0 ? (
          <div className="empty-state">
            <p>No tracking jobs yet.</p>
            <button className="btn btn-primary mt-4" onClick={openAdd}>
              + Add your first job
            </button>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th style={{ width: 36 }}>
                  <input
                    type="checkbox"
                    checked={selected.size === jobs.length && jobs.length > 0}
                    onChange={toggleSelectAll}
                  />
                </th>
                <th>Query</th>
                <th>Target URL</th>
                <th>GL</th>
                <th>HL</th>
                <th>Active</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.has(job.id)}
                      onChange={() => toggleSelect(job.id)}
                    />
                  </td>
                  <td>
                    <Link to={`/jobs/${job.id}`} style={{ color: 'var(--primary)', textDecoration: 'none', fontWeight: 500 }}>
                      {job.query}
                    </Link>
                  </td>
                  <td style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {job.target_url}
                  </td>
                  <td>{job.gl}</td>
                  <td>{job.hl}</td>
                  <td>
                    <span
                      className={`badge ${job.active ? 'badge-success' : 'badge-neutral'}`}
                      style={{ cursor: 'pointer' }}
                      onClick={() => toggleActive(job)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => { if (e.key === 'Enter') toggleActive(job); }}
                    >
                      {job.active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>
                    <div className="flex gap-2">
                      <button className="btn btn-sm btn-outline" onClick={() => openEdit(job)}>
                        Edit
                      </button>
                      <button className="btn btn-sm btn-danger" onClick={() => handleDelete(job)}>
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Add / Edit Modal */}
      {modalOpen && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>{editingJob ? 'Edit Job' : 'Add Job'}</h2>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label htmlFor="job-target-url">Target URL</label>
                <input
                  id="job-target-url"
                  name="target_url"
                  type="url"
                  required
                  placeholder="https://example.com/page"
                  value={form.target_url}
                  onChange={handleChange}
                />
              </div>
              <div className="form-group">
                <label htmlFor="job-query">Query</label>
                <input
                  id="job-query"
                  name="query"
                  type="text"
                  required
                  placeholder="search keyword"
                  value={form.query}
                  onChange={handleChange}
                />
              </div>
              <div className="flex gap-4">
                <div className="form-group" style={{ flex: 1 }}>
                  <label htmlFor="job-gl">GL (country)</label>
                  <input
                    id="job-gl"
                    name="gl"
                    type="text"
                    required
                    placeholder="us"
                    value={form.gl}
                    onChange={handleChange}
                  />
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label htmlFor="job-hl">HL (language)</label>
                  <input
                    id="job-hl"
                    name="hl"
                    type="text"
                    required
                    placeholder="en"
                    value={form.hl}
                    onChange={handleChange}
                  />
                </div>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-outline" onClick={closeModal}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? 'Saving...' : editingJob ? 'Update' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
