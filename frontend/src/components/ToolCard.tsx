import { useNavigate } from 'react-router-dom';
import type { ToolDef } from '../tools/registry';

export function ToolCard({ tool }: { tool: ToolDef }) {
  const nav = useNavigate();

  return (
    <button className="tool-card" onClick={() => nav(tool.path)}>
      <div className="tool-card-icon" style={{ background: tool.color }}>
        <span>{tool.icon}</span>
      </div>
      <div className="tool-card-body">
        <h3 className="tool-card-name">{tool.name}</h3>
        <p className="tool-card-desc">{tool.description}</p>
      </div>
      <span className="tool-card-arrow">→</span>
    </button>
  );
}
