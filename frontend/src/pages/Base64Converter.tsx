import { useState, useRef } from 'react';

type Mode = 'encode' | 'decode';

export default function Base64Converter() {
  const [mode, setMode] = useState<Mode>('encode');
  const [input, setInput] = useState('');
  const [output, setOutput] = useState('');
  const [error, setError] = useState('');
  const [fileResult, setFileResult] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const convert = () => {
    setError('');
    try {
      if (mode === 'encode') {
        setOutput(btoa(unescape(encodeURIComponent(input))));
      } else {
        setOutput(decodeURIComponent(escape(atob(input.trim()))));
      }
    } catch {
      setError(mode === 'encode' ? 'Could not encode the input' : 'Invalid Base64 string');
      setOutput('');
    }
  };

  const swap = () => {
    setMode(m => (m === 'encode' ? 'decode' : 'encode'));
    setInput(output);
    setOutput('');
    setError('');
  };

  const clear = () => {
    setInput('');
    setOutput('');
    setError('');
    setFileResult('');
    if (fileRef.current) fileRef.current.value = '';
  };

  const copy = () => {
    if (output) navigator.clipboard.writeText(output);
  };

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    if (mode === 'encode') {
      reader.onload = () => {
        const base64 = (reader.result as string).split(',')[1] || '';
        setFileResult(base64);
        setOutput(base64);
      };
      reader.readAsDataURL(file);
    } else {
      reader.onload = () => {
        try {
          const text = reader.result as string;
          setOutput(decodeURIComponent(escape(atob(text.trim()))));
          setFileResult(output);
        } catch {
          setError('File does not contain valid Base64');
        }
      };
      reader.readAsText(file);
    }
  };

  return (
    <div className="tool-page tool-page--base64">
      <div className="b64-toolbar">
        <div className="b64-mode-toggle">
          <button
            className={`tool-btn ${mode === 'encode' ? 'tool-btn--primary' : ''}`}
            onClick={() => { setMode('encode'); setError(''); }}
          >
            Encode
          </button>
          <button
            className={`tool-btn ${mode === 'decode' ? 'tool-btn--primary' : ''}`}
            onClick={() => { setMode('decode'); setError(''); }}
          >
            Decode
          </button>
        </div>
        <div className="b64-actions">
          <button className="tool-btn tool-btn--primary" onClick={convert}>
            {mode === 'encode' ? 'Encode →' : '← Decode'}
          </button>
          <button className="tool-btn" onClick={swap} title="Swap input/output">⇄ Swap</button>
          <button className="tool-btn" onClick={clear}>Clear</button>
        </div>
      </div>

      {error && <div className="tool-error">⚠️ {error}</div>}

      <div className="b64-panels">
        <div className="b64-panel">
          <div className="panel-header">
            <span className="panel-title">{mode === 'encode' ? 'Plain Text' : 'Base64'}</span>
            <span className="panel-badge">{input.length} chars</span>
          </div>
          <textarea
            className="b64-textarea"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder={mode === 'encode' ? 'Enter text to encode…' : 'Paste Base64 string…'}
            spellCheck={false}
          />
        </div>

        <div className="b64-panel">
          <div className="panel-header">
            <span className="panel-title">{mode === 'encode' ? 'Base64' : 'Plain Text'}</span>
            <span className="panel-badge">
              {output && <button className="copy-link" onClick={copy}>⎘ Copy</button>}
            </span>
          </div>
          <textarea
            className="b64-textarea b64-textarea--output"
            value={output}
            readOnly
            placeholder="Result will appear here…"
          />
        </div>
      </div>

      <div className="b64-file-section">
        <label className="b64-file-label">
          📁 Or {mode === 'encode' ? 'encode' : 'decode'} a file:
          <input ref={fileRef} type="file" onChange={handleFile} className="b64-file-input" />
        </label>
        {fileResult && (
          <div className="b64-file-result">
            <span className="panel-badge">{fileResult.length} chars</span>
          </div>
        )}
      </div>
    </div>
  );
}
