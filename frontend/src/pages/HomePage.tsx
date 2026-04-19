import { tools } from '../tools/registry';
import { ToolCard } from '../components/ToolCard';

export default function HomePage() {
  return (
    <div className="home-page">
      <div className="home-hero">
        <h1 className="home-title">Dev Toolbox</h1>
        <p className="home-subtitle">Pick a tool to get started</p>
      </div>
      <div className="tool-grid">
        {tools.map(t => (
          <ToolCard key={t.id} tool={t} />
        ))}
      </div>
    </div>
  );
}
