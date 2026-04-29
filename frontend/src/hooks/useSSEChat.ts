import { useCallback, useEffect, useRef, useState } from 'react';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
  stage?: string;
}

export interface ChatMeta {
  inputTokens: number;
  outputTokens: number;
  latencyMs: number;
  toolsCalled: string[];
  model: string;
}

const SESSION_KEY = 'md_reader_session_id';

/**
 * UUID v4 generator that works in both secure (HTTPS) and non-secure (HTTP)
 * contexts. Falls back to crypto.getRandomValues() when randomUUID() is
 * unavailable (HTTP pages are not "secure contexts").
 */
function uuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    try { return crypto.randomUUID(); } catch { /* fall through */ }
  }
  // Fallback: RFC-4122 v4 using getRandomValues (works on HTTP)
  const buf = new Uint8Array(16);
  crypto.getRandomValues(buf);
  buf[6] = (buf[6] & 0x0f) | 0x40;
  buf[8] = (buf[8] & 0x3f) | 0x80;
  const h = Array.from(buf).map(b => b.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;
}

/**
 * Decode the escaped text from the backend SSE _sse_data() helper.
 * The backend escapes: \ → \\ and \n → \n (two chars: backslash + n).
 * This decoder reverses that in a single pass.
 */
function decodeToken(raw: string): string {
  let out = '';
  let i = 0;
  while (i < raw.length) {
    if (raw[i] === '\\' && i + 1 < raw.length) {
      const next = raw[i + 1];
      if (next === 'n') { out += '\n'; i += 2; }
      else if (next === '\\') { out += '\\'; i += 2; }
      else { out += raw[i++]; }
    } else {
      out += raw[i++];
    }
  }
  return out;
}


export function useSSEChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [lastMeta, setLastMeta] = useState<ChatMeta | null>(null);
  const [isRestoring, setIsRestoring] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(
    localStorage.getItem(SESSION_KEY)
  );
  const sessionIdRef = useRef<string | null>(
    localStorage.getItem(SESSION_KEY)
  );
  const abortRef = useRef<AbortController | null>(null);
  // Tracks the active send so stale finally-blocks don't clobber newer state
  const activeSendRef = useRef<string | null>(null);

  // ── Restore chat history on mount if we have a saved session ──
  useEffect(() => {
    const savedId = localStorage.getItem(SESSION_KEY);
    if (!savedId) return;

    let cancelled = false;
    setIsRestoring(true);

    fetch(`/chat/history/${encodeURIComponent(savedId)}`)
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (cancelled || !data?.messages?.length) {
          setIsRestoring(false);
          return;
        }
        sessionIdRef.current = data.session_id;
        setSessionId(data.session_id);
        localStorage.setItem(SESSION_KEY, data.session_id);

        // Convert backend history to Message[]
        const restored: Message[] = data.messages.map(
          (m: { role: string; content: string }, i: number) => ({
            id: `restored-${i}`,
            role: m.role as 'user' | 'assistant',
            content: m.content,
          })
        );
        setMessages(restored);
        setIsRestoring(false);
      })
      .catch(() => {
        if (!cancelled) setIsRestoring(false);
      });

    return () => { cancelled = true; };
  }, []);

  // ── Save session & notify backend on tab close ──
  useEffect(() => {
    const onBeforeUnload = () => {
      const sid = sessionIdRef.current;
      if (!sid) return;
      // Use sendBeacon for reliable delivery during page unload
      navigator.sendBeacon(
        '/chat/disconnect',
        new Blob(
          [JSON.stringify({ session_id: sid })],
          { type: 'application/json' }
        )
      );
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, []);

  const sendMessage = useCallback(async (userText: string, document: string) => {
    if (!userText.trim()) return;

    // Abort any in-progress stream and finalize its streaming message so the
    // UI doesn't show a dangling spinner while the new request loads.
    if (abortRef.current) {
      abortRef.current.abort();
      setMessages(prev =>
        prev.map(m => m.isStreaming ? { ...m, isStreaming: false, stage: undefined } : m)
      );
    }

    const sendId = uuid();
    activeSendRef.current = sendId;

    const userMsg: Message = { id: uuid(), role: 'user', content: userText };
    const assistantId = uuid();
    const assistantMsg: Message = { id: assistantId, role: 'assistant', content: '', isStreaming: true };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setIsLoading(true);

    abortRef.current = new AbortController();

    try {
      const res = await fetch('/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(sessionIdRef.current ? { 'X-Session-ID': sessionIdRef.current } : {}),
        },
        body: JSON.stringify({ message: userText, document, session_id: sessionIdRef.current }),
        signal: abortRef.current.signal,
      });

      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      outer: while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE events are separated by double newlines
        const events = buffer.split('\n\n');
        buffer = events.pop() ?? '';

        for (const rawEvent of events) {
          const lines = rawEvent.split('\n');
          let eventType = 'message';
          let data = '';

          for (const line of lines) {
            if (line.startsWith('event: ')) eventType = line.slice(7).trim();
            else if (line.startsWith('data: ')) data = line.slice(6);
          }

          if (eventType === 'done' || data === '[DONE]') break outer;

          if (eventType === 'thinking') {
            try {
              const p = JSON.parse(data) as { stage: string; detail?: string };
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, stage: p.detail ?? p.stage } : m)
              );
            } catch { /* ignore malformed */ }
            continue;
          }

          if (eventType === 'metadata') {
            try {
              const p = JSON.parse(data) as {
                session_id: string; model: string;
                input_tokens: number; output_tokens: number;
                latency_ms: number; tools_called: string[];
              };
              sessionIdRef.current = p.session_id;
              setSessionId(p.session_id);
              localStorage.setItem(SESSION_KEY, p.session_id);
              setLastMeta({
                inputTokens: p.input_tokens,
                outputTokens: p.output_tokens,
                latencyMs: p.latency_ms,
                toolsCalled: p.tools_called,
                model: p.model,
              });
            } catch { /* ignore malformed */ }
            continue;
          }

          // Plain text token — decode escape sequences
          const token = decodeToken(data);
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId
                ? { ...m, content: m.content + token, stage: undefined }
                : m
            )
          );
        }
      }
    } catch (e: unknown) {
      if ((e as Error).name !== 'AbortError' && activeSendRef.current === sendId) {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? { ...m, content: '⚠️ Could not reach the server. Is the backend running?', isStreaming: false }
              : m
          )
        );
      }
    } finally {
      if (activeSendRef.current === sendId) {
        setMessages(prev =>
          prev.map(m => m.id === assistantId ? { ...m, isStreaming: false, stage: undefined } : m)
        );
        setIsLoading(false);
      }
    }
  }, []);

  const clearChat = useCallback(() => {
    setMessages([]);
    sessionIdRef.current = null;
    setSessionId(null);
    localStorage.removeItem(SESSION_KEY);
    setLastMeta(null);
  }, []);

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    messages,
    isLoading,
    isRestoring,
    lastMeta,
    sessionId,
    sendMessage,
    clearChat,
    stopStreaming,
  };
}
