import { useState, useCallback, useMemo, useEffect } from 'react';
import { broadcastToolContent } from '../hooks/useToolContent';

type ViewMode = 'text' | 'tree' | 'table';

/* ── Tree Node (recursive collapsible view) ── */
function TreeNode({ label, value, path, search }: {
  label: string;
  value: unknown;
  path: string;
  search: string;
}) {
  const [open, setOpen] = useState(true);
  const isObj = value !== null && typeof value === 'object';
  const isArray = Array.isArray(value);
  const entries = isObj ? Object.entries(value as Record<string, unknown>) : [];
  const matchesSearch = search && (
    label.toLowerCase().includes(search) ||
    (!isObj && String(value).toLowerCase().includes(search))
  );

  const typeClass = value === null ? 'jt-null'
    : typeof value === 'boolean' ? 'jt-bool'
    : typeof value === 'number' ? 'jt-num'
    : typeof value === 'string' ? 'jt-str'
    : '';

  if (!isObj) {
    return (
      <div className={`jt-leaf${matchesSearch ? ' jt-hl' : ''}`}>
        <span className="jt-key">{label}</span>
        <span className="jt-colon">: </span>
        <span className={typeClass}>
          {value === null ? 'null' : typeof value === 'string' ? `"${value}"` : String(value)}
        </span>
      </div>
    );
  }

  const bracket = isArray ? ['[', ']'] : ['{', '}'];

  return (
    <div className="jt-node">
      <div
        className={`jt-row${matchesSearch ? ' jt-hl' : ''}`}
        onClick={() => setOpen(o => !o)}
      >
        <span className="jt-toggle">{open ? '▾' : '▸'}</span>
        <span className="jt-key">{label}</span>
        <span className="jt-colon">: </span>
        <span className="jt-bracket">{bracket[0]}</span>
        {!open && (
          <span className="jt-collapsed">
            {' '}{entries.length} {isArray ? 'items' : 'keys'}{' '}{bracket[1]}
          </span>
        )}
      </div>
      {open && (
        <div className="jt-children">
          {entries.map(([k, v]) => (
            <TreeNode
              key={k}
              label={isArray ? k : k}
              value={v}
              path={`${path}.${k}`}
              search={search}
            />
          ))}
          <div className="jt-bracket">{bracket[1]}</div>
        </div>
      )}
    </div>
  );
}

/* ── Table View (for arrays of objects) ── */
function TableView({ data, search }: { data: unknown; search: string }) {
  const rows = Array.isArray(data) ? data : [data];
  const allKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const row of rows) {
      if (row && typeof row === 'object' && !Array.isArray(row)) {
        Object.keys(row as Record<string, unknown>).forEach(k => keys.add(k));
      }
    }
    return Array.from(keys);
  }, [rows]);

  if (allKeys.length === 0) {
    return <div className="json-table-empty">Not a tabular structure (need array of objects)</div>;
  }

  const matchCell = (v: unknown) =>
    search && String(v ?? '').toLowerCase().includes(search);

  return (
    <div className="json-table-wrap">
      <table className="json-table">
        <thead>
          <tr>
            <th className="json-table-idx">#</th>
            {allKeys.map(k => (
              <th key={k} className={search && k.toLowerCase().includes(search) ? 'jt-hl' : ''}>
                {k}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const r = (row && typeof row === 'object' && !Array.isArray(row))
              ? row as Record<string, unknown>
              : {};
            return (
              <tr key={i}>
                <td className="json-table-idx">{i}</td>
                {allKeys.map(k => {
                  const v = r[k];
                  const display = v === undefined ? ''
                    : v === null ? 'null'
                    : typeof v === 'object' ? JSON.stringify(v)
                    : String(v);
                  return (
                    <td key={k} className={matchCell(display) ? 'jt-hl' : ''}>
                      {display}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ── Main Component ── */
export default function JsonFormatter() {
  const [input, setInput] = useState('');
  const [error, setError] = useState('');
  const [indentSize, setIndentSize] = useState(2);
  const [viewMode, setViewMode] = useState<ViewMode>('text');
  const [search, setSearch] = useState('');
  const [copied, setCopied] = useState(false);

  // Broadcast current content to ChatBot whenever it changes
  useEffect(() => {
    broadcastToolContent(input, 'json-formatter', 'JSON Formatter');
  }, [input]);

  const parsed = useMemo(() => {
    if (!input.trim()) return undefined;
    try { return JSON.parse(input); } catch { return undefined; }
  }, [input]);

  const formatted = useMemo(() => {
    if (parsed === undefined) return '';
    return JSON.stringify(parsed, null, indentSize);
  }, [parsed, indentSize]);

  const format = () => {
    setError('');
    if (!input.trim()) return;
    try {
      const p = JSON.parse(input);
      setInput(JSON.stringify(p, null, indentSize));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const minify = () => {
    setError('');
    try {
      const p = JSON.parse(input);
      setInput(JSON.stringify(p));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const clear = () => { setInput(''); setError(''); setSearch(''); };

  const copy = () => {
    const text = formatted || input;
    if (text) {
      navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  const loadSample = () => {
    const sample = {
      name: "Dev Toolbox",
      version: "1.0.0",
      tools: [
        { id: 1, name: "Markdown Reader", status: "active" },
        { id: 2, name: "JSON Formatter", status: "active" },
        { id: 3, name: "Parquet Reader", status: "active" },
        { id: 4, name: "Base64 Converter", status: "active" },
      ],
      config: { theme: "dark", autoFormat: true, indent: 2 },
    };
    setInput(JSON.stringify(sample, null, 2));
    setError('');
  };

  const searchLower = search.toLowerCase();

  /* Highlight matching text in formatted output */
  const highlightText = useCallback((text: string) => {
    if (!searchLower || !text) return text;
    const parts: (string | JSX.Element)[] = [];
    let lastIdx = 0;
    const lower = text.toLowerCase();
    let idx = lower.indexOf(searchLower);
    let key = 0;
    while (idx !== -1) {
      if (idx > lastIdx) parts.push(text.slice(lastIdx, idx));
      parts.push(
        <mark key={key++} className="jt-search-mark">
          {text.slice(idx, idx + searchLower.length)}
        </mark>
      );
      lastIdx = idx + searchLower.length;
      idx = lower.indexOf(searchLower, lastIdx);
    }
    if (lastIdx < text.length) parts.push(text.slice(lastIdx));
    return <>{parts}</>;
  }, [searchLower]);

  return (
    <div className="tool-page tool-page--json">
      <div className="json-toolbar">
        <div className="json-toolbar-left">
          <button className="tool-btn tool-btn--primary" onClick={format}>Format</button>
          <button className="tool-btn" onClick={minify}>Minify</button>
          <button className="tool-btn" onClick={loadSample}>Sample</button>
          <button className="tool-btn" onClick={clear}>Clear</button>
          <button className="tool-btn" onClick={copy}>
            {copied ? '✓ Copied' : '⎘ Copy'}
          </button>
          <label className="tool-label">
            Indent:
            <select
              className="tool-select"
              value={indentSize}
              onChange={e => setIndentSize(Number(e.target.value))}
            >
              <option value={2}>2</option>
              <option value={4}>4</option>
            </select>
          </label>
        </div>
        <div className="json-toolbar-right">
          <div className="json-search-box">
            <span className="json-search-icon">🔍</span>
            <input
              className="json-search-input"
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search..."
            />
            {search && (
              <button className="json-search-clear" onClick={() => setSearch('')}>✕</button>
            )}
          </div>
          <div className="json-view-tabs">
            {(['text', 'tree', 'table'] as ViewMode[]).map(m => (
              <button
                key={m}
                className={`json-view-tab${viewMode === m ? ' json-view-tab--active' : ''}`}
                onClick={() => setViewMode(m)}
              >
                {m === 'text' ? '{ }' : m === 'tree' ? '🌳' : '⊞'} {m.charAt(0).toUpperCase() + m.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <div className="tool-error">⚠️ {error}</div>}

      <div className="json-panels">
        {/* Left: input */}
        <div className="json-panel">
          <div className="panel-header">
            <span className="panel-title">Input</span>
            <span className="panel-badge">{input.length} chars</span>
          </div>
          <textarea
            className="json-textarea"
            value={input}
            onChange={e => { setInput(e.target.value); setError(''); }}
            placeholder="Paste or type JSON here..."
            spellCheck={false}
          />
        </div>

        {/* Right: output in selected view mode */}
        <div className="json-panel">
          <div className="panel-header">
            <span className="panel-title">
              {viewMode === 'text' ? 'Formatted' : viewMode === 'tree' ? 'Tree View' : 'Table View'}
            </span>
            {parsed !== undefined && (
              <span className="panel-badge">
                {Array.isArray(parsed) ? `${parsed.length} items` : typeof parsed === 'object' && parsed ? `${Object.keys(parsed).length} keys` : typeof parsed}
              </span>
            )}
          </div>

          {viewMode === 'text' && (
            <div className="json-text-output">
              {formatted ? (
                <pre className="json-text-pre">{highlightText(formatted)}</pre>
              ) : (
                <div className="json-text-empty">Formatted JSON will appear here...</div>
              )}
            </div>
          )}

          {viewMode === 'tree' && (
            <div className="json-tree-output">
              {parsed !== undefined ? (
                <TreeNode label="root" value={parsed} path="" search={searchLower} />
              ) : (
                <div className="json-text-empty">Enter valid JSON to see the tree view</div>
              )}
            </div>
          )}

          {viewMode === 'table' && (
            <div className="json-tree-output">
              {parsed !== undefined ? (
                <TableView data={parsed} search={searchLower} />
              ) : (
                <div className="json-text-empty">Enter valid JSON to see the table view</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
