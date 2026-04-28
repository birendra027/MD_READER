import { useState, useEffect } from 'react';
import * as yaml from 'js-yaml';
import { broadcastToolContent } from '../hooks/useToolContent';

type Mode = 'json-to-yaml' | 'yaml-to-json';

export default function JsonYamlConverter() {
  const [mode, setMode] = useState<Mode>('json-to-yaml');
  const [input, setInput] = useState('');
  const [output, setOutput] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  const convert = (overrideMode?: Mode, text?: string) => {
    const m = overrideMode ?? mode;
    const src = (text ?? input).trim();
    setError('');
    setOutput('');

    if (!src) return;

    try {
      if (m === 'json-to-yaml') {
        const parsed = JSON.parse(src);
        setOutput(yaml.dump(parsed, { indent: 2, lineWidth: -1 }));
      } else {
        const parsed = yaml.load(src);
        setOutput(JSON.stringify(parsed, null, 2));
      }
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const swap = () => {
    const newMode: Mode = mode === 'json-to-yaml' ? 'yaml-to-json' : 'json-to-yaml';
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
    if (!output) return;
    navigator.clipboard.writeText(output);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  // Broadcast current content to ChatBot
  useEffect(() => {
    const combined = input + (output ? `\n\n--- Output ---\n${output}` : '');
    broadcastToolContent(combined, 'json-yaml', 'JSON ↔ YAML');
  }, [input, output]);

  const inputLabel  = mode === 'json-to-yaml' ? 'JSON' : 'YAML';
  const outputLabel = mode === 'json-to-yaml' ? 'YAML' : 'JSON';

  return (
    <div className="tool-page tool-page--base64">
      <div className="b64-layout">
        {/* Sidebar */}
        <div className="b64-sidebar">
          <button
            className={`b64-side-btn ${mode === 'json-to-yaml' ? 'b64-side-btn--active' : ''}`}
            onClick={() => { setMode('json-to-yaml'); setError(''); convert('json-to-yaml'); }}
          >
            JSON → YAML
          </button>
          <button
            className={`b64-side-btn ${mode === 'yaml-to-json' ? 'b64-side-btn--active' : ''}`}
            onClick={() => { setMode('yaml-to-json'); setError(''); convert('yaml-to-json'); }}
          >
            YAML → JSON
          </button>
          <button className="b64-side-btn b64-side-btn--swap" onClick={swap} title="Swap input ↔ output">
            ⇄ Swap
          </button>
          <button className="b64-side-btn b64-side-btn--clear" onClick={clear}>
            Clear
          </button>
        </div>

        {/* Panels */}
        <div className="b64-main">
          {error && <div className="tool-error">⚠️ {error}</div>}
          <div className="b64-panels">
            <div className="b64-panel">
              <div className="panel-header">
                <span className="panel-title">{inputLabel}</span>
                <span className="panel-badge">{input.length} chars</span>
              </div>
              <textarea
                className="b64-textarea"
                value={input}
                onChange={e => { setInput(e.target.value); convert(undefined, e.target.value); }}
                placeholder={`Paste ${inputLabel} here...`}
                spellCheck={false}
              />
            </div>

            <div className="b64-panel">
              <div className="panel-header">
                <span className="panel-title">{outputLabel}</span>
                <span className="panel-badge">
                  {output && (
                    <button className="copy-link" onClick={copy}>
                      {copied ? '✓ Copied' : '⎘ Copy'}
                    </button>
                  )}
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
