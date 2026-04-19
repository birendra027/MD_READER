import { useState } from 'react';

export default function JsonFormatter() {
  const [input, setInput] = useState('');
  const [output, setOutput] = useState('');
  const [error, setError] = useState('');
  const [indentSize, setIndentSize] = useState(2);

  const format = () => {
    setError('');
    try {
      const parsed = JSON.parse(input);
      setOutput(JSON.stringify(parsed, null, indentSize));
    } catch (e) {
      setError((e as Error).message);
      setOutput('');
    }
  };

  const minify = () => {
    setError('');
    try {
      const parsed = JSON.parse(input);
      setOutput(JSON.stringify(parsed));
    } catch (e) {
      setError((e as Error).message);
      setOutput('');
    }
  };

  const clear = () => {
    setInput('');
    setOutput('');
    setError('');
  };

  const copy = () => {
    if (output) navigator.clipboard.writeText(output);
  };

  const loadSample = () => {
    const sample = {
      name: "Dev Toolbox",
      version: "1.0.0",
      tools: ["markdown", "json-formatter", "parquet-reader", "base64"],
      config: { theme: "dark", autoFormat: true },
    };
    setInput(JSON.stringify(sample));
    setError('');
    setOutput('');
  };

  return (
    <div className="tool-page tool-page--json">
      <div className="json-toolbar">
        <div className="json-toolbar-left">
          <button className="tool-btn tool-btn--primary" onClick={format}>Format</button>
          <button className="tool-btn" onClick={minify}>Minify</button>
          <button className="tool-btn" onClick={loadSample}>Sample</button>
          <button className="tool-btn" onClick={clear}>Clear</button>
        </div>
        <div className="json-toolbar-right">
          <label className="tool-label">
            Indent:
            <select
              className="tool-select"
              value={indentSize}
              onChange={e => setIndentSize(Number(e.target.value))}
            >
              <option value={2}>2 spaces</option>
              <option value={4}>4 spaces</option>
              <option value={1}>Tab</option>
            </select>
          </label>
        </div>
      </div>

      {error && <div className="tool-error">⚠️ {error}</div>}

      <div className="json-panels">
        <div className="json-panel">
          <div className="panel-header">
            <span className="panel-title">Input</span>
            <span className="panel-badge">{input.length} chars</span>
          </div>
          <textarea
            className="json-textarea"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Paste or type JSON here…"
            spellCheck={false}
          />
        </div>

        <div className="json-panel">
          <div className="panel-header">
            <span className="panel-title">Output</span>
            <span className="panel-badge">
              {output && <button className="copy-link" onClick={copy}>⎘ Copy</button>}
            </span>
          </div>
          <textarea
            className="json-textarea json-textarea--output"
            value={output}
            readOnly
            placeholder="Formatted JSON will appear here…"
          />
        </div>
      </div>
    </div>
  );
}
