import { useState, Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { ChatBot } from './components/ChatBot';
import { tools } from './tools/registry';

const HomePage = lazy(() => import('./pages/HomePage'));

// Lazy-load each tool page from registry
const toolRoutes = tools.map(t => ({
  path: t.path,
  Component: lazy(t.component),
}));

function Layout() {
  const [chatOpen, setChatOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const isHome = location.pathname === '/';

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-logo" onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>
          <span className="logo-icon">&#x1F9F0;</span>
          <span className="logo-text">Dev Toolbox</span>
        </div>

        <div className="header-actions">
          {!isHome && (
            <button className="back-btn" onClick={() => navigate('/')}>
              &larr; All Tools
            </button>
          )}
          <button
            className={`chat-toggle-btn ${chatOpen ? 'active' : ''}`}
            onClick={() => setChatOpen(o => !o)}
          >
            {chatOpen ? '✕ Close Chat' : '💬 Chat'}
          </button>
        </div>
      </header>

      <main className="app-main">
        <Suspense fallback={<div className="tool-loading">Loading...</div>}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            {toolRoutes.map(r => (
              <Route key={r.path} path={r.path} element={<r.Component />} />
            ))}
          </Routes>
        </Suspense>
      </main>

      {/* Floating Chat Panel - always independent */}
      {chatOpen && (
        <ChatBot document="" onClose={() => setChatOpen(false)} />
      )}
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  );
}
