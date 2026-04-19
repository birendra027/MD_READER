import type { WSStatus } from '../hooks/useMarkdownWS';

interface Props {
  html: string;
  status: WSStatus;
}

const STATUS_LABELS: Record<WSStatus, string> = {
  connecting: '⟳ Connecting…',
  connected: '● Live',
  disconnected: '○ Disconnected',
};

export function MarkdownPreview({ html, status }: Props) {
  return (
    <div className="preview-panel">
      <div className="panel-header">
        <span className="panel-title">Preview</span>
        <span className={`ws-status ws-status--${status}`}>{STATUS_LABELS[status]}</span>
      </div>
      <div
        className="preview-content"
        dangerouslySetInnerHTML={{
          __html: html || '<p class="preview-placeholder">Preview will appear here…</p>',
        }}
      />
    </div>
  );
}
