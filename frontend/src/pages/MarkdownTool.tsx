import { useState, useRef, useCallback, useEffect } from 'react';
import { MarkdownEditor } from '../components/MarkdownEditor';
import { MarkdownPreview } from '../components/MarkdownPreview';
import { useMarkdownWS } from '../hooks/useMarkdownWS';
import { broadcastToolContent } from '../hooks/useToolContent';

const PLACEHOLDER = `# Welcome to MD Reader

Start writing Markdown here and see it rendered **live** on the right.

## Features

- **Live preview** via WebSocket — updates as you type
- **AI Chatbot** — ask questions about your document
- Slash commands: \`/summarise\`, \`/keypoints\`, \`/overview\`, \`/todo\`

## Example

\`\`\`python
def hello():
    print("Hello, world!")
\`\`\`

> Open the **Chat** panel (top right) and ask: *"What is this document about?"*
`;

export default function MarkdownTool() {
  const [markdown, setMarkdown] = useState(PLACEHOLDER);
  const { html, status, send } = useMarkdownWS();

  const [splitPct, setSplitPct] = useState(50);
  const dragging = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleChange = (val: string) => {
    setMarkdown(val);
    send(val);
    broadcastToolContent(val, 'markdown', 'Markdown Reader');
  };

  // Broadcast initial content when tool mounts
  useEffect(() => {
    broadcastToolContent(markdown, 'markdown', 'Markdown Reader');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setSplitPct(Math.min(80, Math.max(20, pct)));
    };
    const onUp = () => {
      dragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  return (
    <div className="tool-page tool-page--split" ref={containerRef}>
      <div style={{ width: `${splitPct}%`, display: 'flex', overflow: 'hidden', minWidth: 0 }}>
        <MarkdownEditor value={markdown} onChange={handleChange} />
      </div>

      <div className="splitter" onMouseDown={onMouseDown} title="Drag to resize" />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minWidth: 0 }}>
        <MarkdownPreview html={html} status={status} />
      </div>
    </div>
  );
}
