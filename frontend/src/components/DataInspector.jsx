import React, { useState } from 'react';
import { Eye, FileCode, CheckCircle2, AlertTriangle, ArrowRightLeft } from 'lucide-react';

export default function DataInspector({ selectedNode, failureScenario }) {
  const [activeTab, setActiveTab] = useState('input');

  if (!selectedNode) {
    return null;
  }

  const hasInput = selectedNode.input_preview !== undefined && selectedNode.input_preview !== null;
  const hasOutput = selectedNode.output_preview !== undefined && selectedNode.output_preview !== null;
  const hasError = Boolean(selectedNode.error);

  return (
    <div className="glass-panel" style={{ padding: '20px', marginBottom: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
        <div>
          <h3 style={{ fontSize: '0.95rem', fontWeight: '700', color: '#ffffff', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Eye size={18} color="#06b6d4" />
            <span>Inspection Lens: {selectedNode.name}</span>
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            Compare input state, schema divergence, and self-healed payload
          </p>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: '6px', background: 'rgba(0, 0, 0, 0.3)', padding: '4px', borderRadius: '8px' }}>
          <button
            onClick={() => setActiveTab('input')}
            style={{
              padding: '4px 10px',
              borderRadius: '6px',
              border: 'none',
              fontSize: '0.75rem',
              fontWeight: '600',
              cursor: 'pointer',
              background: activeTab === 'input' ? 'rgba(59, 130, 246, 0.3)' : 'transparent',
              color: activeTab === 'input' ? '#60a5fa' : 'var(--text-muted)'
            }}
          >
            Node Input
          </button>
          <button
            onClick={() => setActiveTab('output')}
            style={{
              padding: '4px 10px',
              borderRadius: '6px',
              border: 'none',
              fontSize: '0.75rem',
              fontWeight: '600',
              cursor: 'pointer',
              background: activeTab === 'output' ? 'rgba(16, 185, 129, 0.3)' : 'transparent',
              color: activeTab === 'output' ? '#34d399' : 'var(--text-muted)'
            }}
          >
            Node Output / Healed State
          </button>
          {hasError && (
            <button
              onClick={() => setActiveTab('error')}
              style={{
                padding: '4px 10px',
                borderRadius: '6px',
                border: 'none',
                fontSize: '0.75rem',
                fontWeight: '600',
                cursor: 'pointer',
                background: activeTab === 'error' ? 'rgba(244, 63, 94, 0.3)' : 'transparent',
                color: activeTab === 'error' ? '#fb7185' : 'var(--text-muted)'
              }}
            >
              Intercepted Error
            </button>
          )}
        </div>
      </div>

      <div style={{ 
        background: 'rgba(0, 0, 0, 0.5)', 
        borderRadius: '8px', 
        padding: '14px', 
        maxHeight: '260px', 
        overflowY: 'auto',
        fontFamily: 'var(--font-mono)',
        fontSize: '0.74rem',
        border: '1px solid rgba(255, 255, 255, 0.05)'
      }}>
        {activeTab === 'input' && (
          hasInput ? (
            <pre style={{ margin: 0, color: '#f1f5f9' }}>
              <code>{JSON.stringify(selectedNode.input_preview, null, 2)}</code>
            </pre>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
              No input data passed to this node yet.
            </div>
          )
        )}

        {activeTab === 'output' && (
          hasOutput ? (
            <pre style={{ margin: 0, color: '#34d399' }}>
              <code>{JSON.stringify(selectedNode.output_preview, null, 2)}</code>
            </pre>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
              Node output has not been emitted yet. Run the pipeline to view results.
            </div>
          )
        )}

        {activeTab === 'error' && (
          <div style={{ color: '#fb7185', lineHeight: '1.5' }}>
            <div style={{ fontWeight: '700', marginBottom: '8px' }}>
              ⚠️ Intercepted Exception:
            </div>
            <div>{selectedNode.error}</div>
          </div>
        )}
      </div>
    </div>
  );
}
