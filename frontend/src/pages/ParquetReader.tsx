import { useState, useRef } from 'react';

interface ParquetData {
  columns: string[];
  rows: Record<string, unknown>[];
  numRows: number;
  schema: { name: string; type: string }[];
}

export default function ParquetReader() {
  const [data, setData] = useState<ParquetData | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [fileName, setFileName] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const processingRef = useRef(false);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || processingRef.current) return;

    processingRef.current = true;
    setFileName(file.name);
    setError('');
    setLoading(true);
    setData(null);

    const formData = new FormData();
    formData.append('file', file);

    // Reset input so re-uploading same file works and StrictMode remount doesn't re-fire
    if (fileRef.current) fileRef.current.value = '';

    try {
      const res = await fetch('/api/parquet/read', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Failed to read parquet file');
      }

      const result = await res.json();
      setData(result);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
      processingRef.current = false;
    }
  };

  const clear = () => {
    setData(null);
    setError('');
    setFileName('');
    if (fileRef.current) fileRef.current.value = '';
  };

  return (
    <div className="tool-page tool-page--parquet">
      <div className="parquet-upload-area">
        <input
          ref={fileRef}
          type="file"
          accept=".parquet"
          onChange={handleFile}
          className="parquet-file-input"
          id="parquet-upload"
        />
        <label htmlFor="parquet-upload" className="parquet-drop-zone">
          <span className="parquet-drop-icon">📊</span>
          <span className="parquet-drop-text">
            {fileName ? fileName : 'Click to select a .parquet file'}
          </span>
          <span className="parquet-drop-hint">Supported: Apache Parquet files</span>
        </label>
        {fileName && (
          <button className="tool-btn" onClick={clear} style={{ marginTop: 12 }}>
            Clear
          </button>
        )}
      </div>

      {loading && <div className="tool-loading">Reading parquet file…</div>}
      {error && <div className="tool-error">⚠️ {error}</div>}

      {data && (
        <>
          <div className="parquet-meta">
            <span className="parquet-meta-item">📋 {data.columns.length} columns</span>
            <span className="parquet-meta-item">📄 {data.numRows} rows</span>
          </div>

          {/* Schema */}
          <details className="parquet-section" open>
            <summary className="parquet-section-title">Schema</summary>
            <div className="parquet-schema-scroll">
              <table className="parquet-table">
                <thead>
                  <tr>
                    <th>Column</th>
                    <th>Type</th>
                  </tr>
                </thead>
                <tbody>
                  {data.schema.map((col, i) => (
                    <tr key={i}>
                      <td>{col.name}</td>
                      <td><code>{col.type}</code></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          {/* Data preview */}
          <details className="parquet-section" open>
            <summary className="parquet-section-title">
              Data Preview (showing {data.rows.length} of {data.numRows})
            </summary>
            <div className="parquet-table-scroll">
              <table className="parquet-table">
                <thead>
                  <tr>
                    {data.columns.map(col => (
                      <th key={col}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row, i) => (
                    <tr key={i}>
                      {data.columns.map(col => (
                        <td key={col}>{String(row[col] ?? '')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
