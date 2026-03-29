import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Jobs from './pages/Jobs';
import RunControl from './pages/RunControl';
import RunHistory from './pages/RunHistory';
import RunDetail from './pages/RunDetail';
import JobDetail from './pages/JobDetail';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <nav className="sidebar">
          <h1 className="logo">SERP Tracker</h1>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/jobs">Jobs</NavLink>
          <NavLink to="/run">Run Control</NavLink>
          <NavLink to="/history">Run History</NavLink>
        </nav>
        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/jobs/:id" element={<JobDetail />} />
            <Route path="/run" element={<RunControl />} />
            <Route path="/history" element={<RunHistory />} />
            <Route path="/history/:id" element={<RunDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
