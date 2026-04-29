import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type MouseEvent as ReactMouseEvent } from 'react';
import { useSSEChat } from '../hooks/useSSEChat';
import { ChatMessage } from './ChatMessage';

interface Props {
  document: string;
  isMinimized: boolean;
  onMinimize: () => void;
  onRestore: () => void;
}

const MIN_W = 280;
const MIN_H = 280;
const EDGE = 6; // resize-handle thickness (px)
const SIZE_KEY = 'md_reader_chat_size';

type Edge = 'left' | 'top' | 'top-left';

function loadSavedSize() {
  try {
    const raw = localStorage.getItem(SIZE_KEY);
    if (raw) {
      const { w, h, top, right } = JSON.parse(raw);
      return {
        size: { w: Math.max(MIN_W, w), h: Math.max(MIN_H, h) },
        pos: { top: Math.max(0, top), right: Math.max(0, right) },
      };
    }
  } catch { /* ignore */ }
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const isSmall = vw < 640;
  return {
    size: {
      w: isSmall ? vw : Math.min(420, vw * 0.95),
      h: isSmall ? vh - 52 : vh - 16,  // 52 = header height
    },
    pos: { top: isSmall ? 52 : 8, right: isSmall ? 0 : 8 },
  };
}

export function ChatBot({ document: docContent, isMinimized, onMinimize, onRestore }: Props) {
  const { messages, isLoading, isRestoring, lastMeta, sessionId, sendMessage, clearChat, stopStreaming } = useSSEChat();
  const [input, setInput] = useState('');
  const [files, setFiles] = useState<{ filename: string; url?: string }[]>([]);
  const [filesOpen, setFilesOpen] = useState(false);
  const hasSession = Boolean(sessionId);
  const bottomRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Panel geometry — persisted in localStorage so size survives close/reopen
  const saved = useRef(loadSavedSize());
  const [size, setSize] = useState(saved.current.size);
  const [pos, setPos] = useState(saved.current.pos);
  const dragRef = useRef<{ edge: Edge; startX: number; startY: number; startW: number; startH: number; startTop: number; startRight: number } | null>(null);

  // Persist size whenever it changes
  useEffect(() => {
    localStorage.setItem(SIZE_KEY, JSON.stringify({ ...size, ...pos }));
  }, [size, pos]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const refreshFiles = useCallback(async (sid: string) => {
    try {
      const res = await fetch(`/chat/files/${encodeURIComponent(sid)}`);
      if (!res.ok) return;
      const data = await res.json();
      setFiles(Array.isArray(data?.files) ? data.files : []);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (!sessionId) {
      setFiles([]);
      setFilesOpen(false);
      return;
    }
    void refreshFiles(sessionId);
  }, [sessionId, messages.length, lastMeta?.latencyMs, refreshFiles]);

  // Re-fetch whenever code execution produces files (fired by ChatMessage)
  useEffect(() => {
    const handler = (e: Event) => {
      const sid = (e as CustomEvent<{ sessionId: string }>).detail?.sessionId || sessionId;
      if (sid) void refreshFiles(sid);
    };
    window.addEventListener('md-execution-files-updated', handler);
    return () => window.removeEventListener('md-execution-files-updated', handler);
  }, [sessionId, refreshFiles]);

  // ── Resize drag logic ──
  const onEdgeDown = useCallback((edge: Edge) => (e: ReactMouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragRef.current = {
      edge,
      startX: e.clientX,
      startY: e.clientY,
      startW: size.w,
      startH: size.h,
      startTop: pos.top,
      startRight: pos.right,
    };

    const onMove = (ev: globalThis.MouseEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const dx = ev.clientX - d.startX;
      const dy = ev.clientY - d.startY;

      let newW = d.startW;
      let newH = d.startH;
      let newTop = d.startTop;

      if (d.edge === 'left' || d.edge === 'top-left') {
        newW = Math.max(MIN_W, Math.min(d.startW - dx, window.innerWidth - d.startRight - 4));
      }
      if (d.edge === 'top' || d.edge === 'top-left') {
        newTop = Math.max(0, d.startTop + dy);
        newH = Math.max(MIN_H, d.startH - dy);
      }

      setSize({ w: newW, h: newH });
      setPos(p => ({ ...p, top: newTop }));
    };

    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      globalThis.document.body.style.cursor = '';
      globalThis.document.body.style.userSelect = '';
    };

    globalThis.document.body.style.cursor =
      edge === 'left' ? 'ew-resize' : edge === 'top' ? 'ns-resize' : 'nwse-resize';
    globalThis.document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [size, pos]);

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;
    setInput('');
    sendMessage(text, docContent);
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  useEffect(() => {
    const onClick = (e: globalThis.MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (!target) return;
      if (target.closest('.chat-toggle-btn')) return;
      if (panelRef.current && !panelRef.current.contains(target)) {
        onMinimize();
      }
    };
    const id = setTimeout(() => globalThis.document.addEventListener('mousedown', onClick), 0);
    return () => {
      clearTimeout(id);
      globalThis.document.removeEventListener('mousedown', onClick);
    };
  }, [onMinimize]);

  if (isMinimized) {
    return null;
  }

  return (
    <div
      className="chat-modal"
      ref={panelRef}
      style={{
        width: Math.min(size.w, window.innerWidth),
        height: Math.min(size.h, window.innerHeight - pos.top),
        top: pos.top,
        right: pos.right,
        bottom: 'auto',
        maxWidth: '100vw',
        maxHeight: `calc(100vh - ${pos.top}px)`,
      }}
    >
      {/* Resize handles */}
      <div className="chat-resize chat-resize--left" onMouseDown={onEdgeDown('left')} />
      <div className="chat-resize chat-resize--top" onMouseDown={onEdgeDown('top')} />
      <div className="chat-resize chat-resize--top-left" onMouseDown={onEdgeDown('top-left')} />

      <div className="chat-header">
        <span className="panel-title">💬 Chat Assistant</span>
        <div className="chat-header-actions">
          <div className="chat-header-files">
            <button
              className="chat-files-btn"
              onClick={() => setFilesOpen(open => !open)}
              title="Generated Files"
            >
              <span className="chat-files-icon">📁</span>
              <span className="chat-files-label">Generated Files ({files.length})</span>
            </button>
            {filesOpen && (
              <div className="chat-files-menu">
                {!hasSession && (
                  <div className="chat-files-empty">Start a chat or run code to create session files.</div>
                )}
                {hasSession && files.length === 0 && (
                  <div className="chat-files-empty">No generated files yet for this session.</div>
                )}
                {hasSession && files.map(file => (
                  <a
                    key={file.filename}
                    className="chat-files-item"
                    href={file.url || `/chat/files/${sessionId}/${encodeURIComponent(file.filename)}`}
                    download={file.filename}
                    title={file.filename}
                  >
                    <span className="chat-files-item-icon">📄</span>
                    <span className="chat-files-item-name">{file.filename}</span>
                  </a>
                ))}
              </div>
            )}
          </div>
          {lastMeta && (
            <span className="chat-meta" title={`Model: ${lastMeta.model} · Tools: ${lastMeta.toolsCalled.join(', ') || 'none'}`}>
              {lastMeta.inputTokens + lastMeta.outputTokens} tok · {lastMeta.latencyMs}ms
            </span>
          )}
          <button className="icon-btn" onClick={clearChat} title="Clear conversation">
            🗑 Clear
          </button>
          <button className="icon-btn" onClick={onRestore} title="Restore chat" style={{ display: 'none' }}>
            Restore
          </button>
          <button className="icon-btn icon-btn--close" onClick={onMinimize} title="Minimize chat">
            — Minimize
          </button>
        </div>
      </div>

      <div className="chat-messages">
        {isRestoring && (
          <div className="chat-empty">
            <div className="chat-empty-icon">⏳</div>
            <p>Restoring previous conversation…</p>
          </div>
        )}
        {!isRestoring && messages.length === 0 && (
          <div className="chat-empty">
            <div className="chat-empty-icon">🤖</div>
            <p>Ask anything about your document</p>
            <p className="chat-hint">
              Ask me anything — coding help, tool questions, or try <code>/summarise</code> <code>/keypoints</code> <code>/overview</code>
            </p>
          </div>
        )}
        {messages.map(msg => (
          <ChatMessage key={msg.id} msg={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-area">
        <textarea
          className="chat-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask a question… (Enter to send)"
          rows={3}
          disabled={isLoading && !input}
        />
        <button
          className="send-btn"
          onClick={isLoading && !input.trim() ? stopStreaming : handleSend}
          title={isLoading && !input.trim() ? 'Stop generation' : 'Send message'}
        >
          {isLoading && !input.trim() ? '■ Stop' : '↑ Send'}
        </button>
      </div>
    </div>
  );
}
