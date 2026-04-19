import { useState, useRef, useEffect } from 'react';
import Markdown from 'react-markdown';
import type { Components } from 'react-markdown';
import type { Message } from '../hooks/useSSEChat';

interface CodeBlockProps {
  lang: string;
  code: string;
}

const RUNNABLE = new Set(['python', 'py', 'shell', 'bash', 'sh', 'powershell', 'pwsh', 'cmd']);

function CodeBlock({ lang, code }: CodeBlockProps) {
  const [currentCode, setCurrentCode] = useState(code);
  const [output, setOutput] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState('');
  const [copied, setCopied] = useState(false);
  const [wasFixed, setWasFixed] = useState(false);
  const [success, setSuccess] = useState<boolean | null>(null);
  const [files, setFiles] = useState<{ name: string; sessionId: string }[]>([]);
  const [filesOpen, setFilesOpen] = useState(true);
  const outputRef = useRef<HTMLPreElement>(null);

  const canRun = RUNNABLE.has(lang);

  // Auto-scroll output to bottom while running
  useEffect(() => {
    if (outputRef.current && running) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [output, running]);

  /** Execute code via streaming endpoint with real-time output */
  const runCode = async () => {
    setRunning(true);
    setOutput('');
    setWasFixed(false);
    setSuccess(null);
    setStatus('Running…');
    setFiles([]);

    try {
      const language = lang === 'py' ? 'python'
        : ['bash', 'sh'].includes(lang) ? 'shell'
        : lang;

      const sessionId = localStorage.getItem('md_reader_session_id') || '';

      const res = await fetch('/chat/execute-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: currentCode, language, session_id: sessionId }),
      });

      if (!res.ok || !res.body) {
        setOutput(`⚠️ Server error: ${res.statusText}`);
        setSuccess(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let outputText = '';
      let lastStage = '';

      const append = (text: string) => {
        outputText += text;
        setOutput(outputText);
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE messages (separated by double newlines)
        let idx: number;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const message = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);

          let eventType = '';
          let data = '';
          for (const line of message.split('\n')) {
            if (line.startsWith('event: ')) eventType = line.slice(7);
            else if (line.startsWith('data: ')) data = line.slice(6);
          }
          if (!eventType || !data) continue;

          try {
            if (eventType === 'output') {
              const { text } = JSON.parse(data);
              append(text);
            } else if (eventType === 'status') {
              const { stage, detail } = JSON.parse(data);
              setStatus(detail);
              // Show phase transitions in output (skip plain "running")
              if (stage !== 'running' && stage !== lastStage) {
                append('\n' + '─'.repeat(36) + '\n' + detail + '\n');
              }
              lastStage = stage;
            } else if (eventType === 'fix_code') {
              const { code: fixedCode } = JSON.parse(data);
              setCurrentCode(fixedCode);
              setWasFixed(true);
            } else if (eventType === 'result') {
              const parsed = JSON.parse(data);
              setSuccess(parsed.success);
              if (parsed.files?.length > 0 && parsed.session_id) {
                setFiles(parsed.files.map((f: string) => ({ name: f, sessionId: parsed.session_id })));
              }
              let summary = '';
              if (parsed.auto_installed?.length > 0) {
                summary += '📦 Installed: ' + parsed.auto_installed.join(', ') + '\n';
              }
              if (parsed.was_fixed && parsed.success) {
                summary += '🔧 Code was automatically fixed\n';
              }
              if (parsed.success) summary += '✅ Done';
              else summary += '❌ Could not fix automatically';
              append('\n' + '─'.repeat(36) + '\n' + summary + '\n');
            } else if (eventType === 'error') {
              const { detail } = JSON.parse(data);
              append('\n⚠️ ' + detail + '\n');
              setSuccess(false);
            }
          } catch {
            // Ignore malformed events
          }
        }
      }

      if (!outputText.trim()) setOutput('(no output)');
    } catch (e) {
      setOutput('⚠️ Could not reach server: ' + (e as Error).message);
      setSuccess(false);
    } finally {
      setRunning(false);
      setStatus('');
    }
  };

  const copyCode = () => {
    navigator.clipboard.writeText(currentCode).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const outputClass = running ? 'code-output--live'
    : success === false ? 'code-output--error'
    : 'code-output--ok';

  return (
    <div className="code-block">
      <div className="code-block-header">
        <span className="code-lang">{lang || 'code'}{wasFixed ? ' · 🔧 fixed' : ''}</span>
        <div className="code-block-actions">
          <button className="code-btn" onClick={copyCode} title="Copy code">
            {copied ? '✓ Copied' : '⎘ Copy'}
          </button>
          {canRun && (
            <button
              className={`code-btn code-btn--run ${running ? 'running' : ''}`}
              onClick={runCode}
              disabled={running}
              title="Run code"
            >
              {running ? `⏳ ${status}` : '▶ Run'}
            </button>
          )}
        </div>
      </div>
      <pre className="code-block-pre"><code>{currentCode}</code></pre>
      {output !== null && (
        <div className={`code-output ${outputClass}`}>
          <div className="code-output-label">{running ? 'Live Output' : 'Output'}</div>
          <pre ref={outputRef}>{output}</pre>
        </div>
      )}
      {files.length > 0 && (
        <div className="file-folder">
          <button className="file-folder-header" onClick={() => setFilesOpen(!filesOpen)}>
            <span className="file-folder-icon">{filesOpen ? '📂' : '📁'}</span>
            <span className="file-folder-title">Generated Files ({files.length})</span>
            <span className="file-folder-chevron">{filesOpen ? '▾' : '▸'}</span>
          </button>
          {filesOpen && (
            <ul className="file-folder-list">
              {files.map((f) => (
                <li key={f.name} className="file-folder-item">
                  <span className="file-folder-item-icon">📄</span>
                  <span className="file-folder-item-name">{f.name}</span>
                  <a
                    className="file-folder-download"
                    href={`/chat/files/${f.sessionId}/${encodeURIComponent(f.name)}`}
                    download={f.name}
                    title={`Download ${f.name}`}
                  >
                    ⬇
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

interface Props {
  msg: Message;
}

export function ChatMessage({ msg }: Props) {
  const isUser = msg.role === 'user';

  const components: Components = {
    code({ className, children, ...rest }) {
      const match = /language-(\w+)/.exec(className || '');
      const text = String(children).replace(/\n$/, '');
      const isBlock = match || text.includes('\n');
      if (isBlock) {
        return (
          <CodeBlock
            lang={match ? match[1] : ''}
            code={text}
          />
        );
      }
      return <code className={className} {...rest}>{children}</code>;
    },
  };

  return (
    <div className={`chat-message chat-message--${isUser ? 'user' : 'assistant'}`}>
      {!isUser && msg.stage && (
        <div className="chat-stage">⚙ {msg.stage}</div>
      )}
      <div className="chat-bubble">
        {isUser ? (
          <span>{msg.content}</span>
        ) : (
          <Markdown components={components}>
            {msg.content || ''}
          </Markdown>
        )}
        {msg.isStreaming && !msg.stage && <span className="chat-cursor" />}
      </div>
    </div>
  );
}

