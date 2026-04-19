import type { ComponentType } from 'react';

export interface ToolDef {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;       // accent gradient for card
  path: string;        // route path
  component: () => Promise<{ default: ComponentType }>;
}

export const tools: ToolDef[] = [
  {
    id: 'markdown',
    name: 'Markdown Reader',
    description: 'Write Markdown and see it rendered live with WebSocket preview.',
    icon: '📝',
    color: 'linear-gradient(135deg, #58a6ff, #a78bfa)',
    path: '/markdown',
    component: () => import('../pages/MarkdownTool'),
  },
  {
    id: 'json-formatter',
    name: 'JSON Formatter',
    description: 'Paste or type JSON to format, validate, and explore it visually.',
    icon: '🔧',
    color: 'linear-gradient(135deg, #3fb950, #58a6ff)',
    path: '/json-formatter',
    component: () => import('../pages/JsonFormatter'),
  },
  {
    id: 'parquet-reader',
    name: 'Parquet Reader',
    description: 'Upload and inspect Apache Parquet files — view schema and data.',
    icon: '📊',
    color: 'linear-gradient(135deg, #d29922, #f0883e)',
    path: '/parquet-reader',
    component: () => import('../pages/ParquetReader'),
  },
  {
    id: 'base64',
    name: 'Base64 Converter',
    description: 'Encode and decode text or files with Base64 instantly.',
    icon: '🔄',
    color: 'linear-gradient(135deg, #bc8cff, #f778ba)',
    path: '/base64',
    component: () => import('../pages/Base64Converter'),
  },
];
