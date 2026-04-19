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
  const sessionIdRef = useRef<string | null>(
    localStorage.getItem(SESSION_KEY)
  );
  const abortRef = useRef<AbortController | null>(null);

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
    if (!userText.trim() || isLoading) return;

    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content: userText };
    const assistantId = crypto.randomUUID();
    const assistantMsg: Message = { id: assistantId, role: 'assistant', content: '', isStreaming: true };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setIsLoading(true);

    abortRef.current?.abort();
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
      if ((e as Error).name !== 'AbortError') {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? { ...m, content: '⚠️ Could not reach the server. Is the backend running?', isStreaming: false }
              : m
          )
        );
      }
    } finally {
      setMessages(prev =>
        prev.map(m => m.id === assistantId ? { ...m, isStreaming: false, stage: undefined } : m)
      );
      setIsLoading(false);
    }
  }, [isLoading]);

  const clearChat = useCallback(() => {
    setMessages([]);
    sessionIdRef.current = null;
    localStorage.removeItem(SESSION_KEY);
    setLastMeta(null);
  }, []);

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { messages, isLoading, isRestoring, lastMeta, sendMessage, clearChat, stopStreaming };
}
