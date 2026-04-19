import { useState } from 'react';

type Mode = 'encode' | 'decode';

export default function Base64Converter() {
  const [mode, setMode] = useState<Mode>('encode');
  const [input, setInput] = useState('');
  const [output, setOutput] = useState('');
  const [error, setError] = useState('');

  const convert = (overrideMode?: Mode, text?: string) => {
    const m = overrideMode ?? mode;
    const src = text ?? input;
    setError('');
    try {
      if (m === 'encode') {
        setOutput(btoa(unescape(encodeURIComponent(src))));
      } else {
        setOutput(decodeURIComponent(escape(atob(src.trim()))));
      }
    } catch {
      setError(m === 'encode' ? 'Could not encode the input' : 'Invalid Base64 string');
      setOutput('');
    }
  };

  const swap = () => {
    const newMode: Mode = mode === 'encode' ? 'decode' : 'encode';
    setMode(newMode);
    setInput(output);
    setOutput('');
    setError('');
  };

  const clear = () => {
    setInput('');
    setOutput('');
    setError('');
  };

  const copy = () => {
    if (output) navigator.clipboard.writeText(output);
  };

  return (
    <div className="tool-page tool-page--base64">
      <div className="b64-layout">
        {/* Left sidebar with action buttons */}
        <div className="b64-sidebar">
          <button
            className={`b64-side-btn ${mode === 'encode' ? 'b64-side-btn--active' : ''}`}
            onClick={() => { setMode('encode'); setError(''); convert('encode'); }}
          >
            Encode
          </button>
          <button
            className={`b64-side-btn ${mode === 'decode' ? 'b64-side-btn--active' : ''}`}
            onClick={() => { setMode('decode'); setError(''); convert('decode'); }}
          >
            Decode
          </button>
          <button className="b64-side-btn b64-side-btn--swap" onClick={swap} title="Swap input ↔ output">
            ⇄ Swap
          </button>
          <button className="b64-side-btn b64-side-btn--clear" onClick={clear}>
            Clear
          </button>
        </div>

        {/* Right area with panels */}
        <div className="b64-main">
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
                placeholder={mode === 'encode' ? 'Enter text to encode...' : 'Paste Base64 string...'}
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
                placeholder="Result will appear here..."
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
