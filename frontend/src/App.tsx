import { useEffect, useState, Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { ChatBot } from './components/ChatBot';
import { tools } from './tools/registry';

const HomePage = lazy(() => import('./pages/HomePage'));
const CHAT_OPEN_KEY = 'md_reader_chat_open';
const CHAT_MINIMIZED_KEY = 'md_reader_chat_minimized';

// Lazy-load each tool page from registry
const toolRoutes = tools.map(t => ({
  path: t.path,
  Component: lazy(t.component),
}));

function Layout() {
  const [chatOpen, setChatOpen] = useState(() => localStorage.getItem(CHAT_OPEN_KEY) === '1');
  const [chatMinimized, setChatMinimized] = useState(() => localStorage.getItem(CHAT_MINIMIZED_KEY) === '1');
  const [activeDoc, setActiveDoc] = useState('');
  const navigate = useNavigate();
  const location = useLocation();
  const isHome = location.pathname === '/';

  // Listen for tool pages broadcasting their current content
  useEffect(() => {
    const handler = (e: Event) => {
      const { content } = (e as CustomEvent<{ content: string; toolId: string; toolName: string }>).detail;
      setActiveDoc(content);
    };
    window.addEventListener('md-tool-content', handler);
    return () => window.removeEventListener('md-tool-content', handler);
  }, []);

  // Clear context when navigating back to the home page
  useEffect(() => {
    if (isHome) setActiveDoc('');
  }, [isHome]);

  useEffect(() => {
    localStorage.setItem(CHAT_OPEN_KEY, chatOpen ? '1' : '0');
  }, [chatOpen]);

  useEffect(() => {
    localStorage.setItem(CHAT_MINIMIZED_KEY, chatMinimized ? '1' : '0');
  }, [chatMinimized]);

  const toggleChat = () => {
    if (!chatOpen) {
      setChatOpen(true);
      setChatMinimized(false);
      return;
    }
    setChatMinimized(prev => !prev);
  };

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
            className={`chat-toggle-btn ${chatOpen && !chatMinimized ? 'active' : ''}`}
            onClick={toggleChat}
          >
            {!chatOpen ? '💬 Chat' : chatMinimized ? '💬 Restore Chat' : '— Minimize Chat'}
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
        <ChatBot
          document={activeDoc}
          isMinimized={chatMinimized}
          onMinimize={() => setChatMinimized(true)}
          onRestore={() => setChatMinimized(false)}
        />
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
