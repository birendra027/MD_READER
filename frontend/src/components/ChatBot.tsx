import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type MouseEvent as ReactMouseEvent } from 'react';
import { useSSEChat } from '../hooks/useSSEChat';
import { ChatMessage } from './ChatMessage';

interface Props {
  document: string;
  onClose: () => void;
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

export function ChatBot({ document: docContent, onClose }: Props) {
  const { messages, isLoading, isRestoring, lastMeta, sendMessage, clearChat, stopStreaming } = useSSEChat();
  const [input, setInput] = useState('');
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
    if (!text || isLoading) return;
    setInput('');
    sendMessage(text, docContent);
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Close on click outside ──
  useEffect(() => {
    const onClick = (e: globalThis.MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    // Use setTimeout so the opening click doesn't immediately close it
    const id = setTimeout(() => globalThis.document.addEventListener('mousedown', onClick), 0);
    return () => {
      clearTimeout(id);
      globalThis.document.removeEventListener('mousedown', onClick);
    };
  }, [onClose]);

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
          {lastMeta && (
            <span className="chat-meta" title={`Model: ${lastMeta.model} · Tools: ${lastMeta.toolsCalled.join(', ') || 'none'}`}>
              {lastMeta.inputTokens + lastMeta.outputTokens} tok · {lastMeta.latencyMs}ms
            </span>
          )}
          <button className="icon-btn" onClick={clearChat} title="Clear conversation">
            🗑 Clear
          </button>
          <button className="icon-btn icon-btn--close" onClick={onClose} title="Close chat">
            ✕ Close
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
          onClick={isLoading ? stopStreaming : handleSend}
          title={isLoading ? 'Stop generation' : 'Send message'}
        >
          {isLoading ? '■ Stop' : '↑ Send'}
        </button>
      </div>
    </div>
  );
}
