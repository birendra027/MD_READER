import { useRef, type KeyboardEvent } from 'react';

interface Props {
  value: string;
  onChange: (val: string) => void;
}

export function MarkdownEditor({ value, onChange }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const ta = textareaRef.current!;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const next = value.substring(0, start) + '  ' + value.substring(end);
      onChange(next);
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 2;
      });
    }
  };

  const words = value.trim() ? value.trim().split(/\s+/).length : 0;
  const chars = value.length;

  return (
    <div className="editor-panel">
      <div className="panel-header">
        <span className="panel-title">Editor</span>
        <span className="panel-badge">{words}w · {chars}c</span>
      </div>
      <textarea
        ref={textareaRef}
        className="editor-textarea"
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Start typing Markdown…"
        spellCheck={false}
      />
    </div>
  );
}
