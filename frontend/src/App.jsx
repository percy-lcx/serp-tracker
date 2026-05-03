import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Jobs from './pages/Jobs';
import RunControl from './pages/RunControl';
import RunDetail from './pages/RunDetail';
import JobDetail from './pages/JobDetail';
import Settings from './pages/Settings';
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
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/jobs/:id" element={<JobDetail />} />
            <Route path="/run" element={<RunControl />} />
            <Route path="/history/:id" element={<RunDetail />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
