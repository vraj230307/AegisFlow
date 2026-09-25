import React from 'react';
import { 
  Database, RefreshCw, Cpu, CheckSquare, HardDrive, 
  AlertTriangle, Wrench, ShieldAlert, Sparkles, ArrowRight 
} from 'lucide-react';

export default function PipelineGraph({ nodes, selectedNodeId, onSelectNode }) {
  const getNodeIcon = (nodeId, status) => {
    if (status === 'failed') return <ShieldAlert size={20} color="#fb7185" />;
    if (status === 'healing') return <Wrench size={20} color="#fbbf24" className="anim-healing" />;
    if (status === 'patching') return <Sparkles size={20} color="#c084fc" />;

    switch (nodeId) {
      case 'node_extract': return <Database size={20} color="#38bdf8" />;
      case 'node_cleanse': return <RefreshCw size={20} color="#a78bfa" />;
      case 'node_enrich': return <Cpu size={20} color="#34d399" />;
      case 'node_verify': return <CheckSquare size={20} color="#fbbf24" />;
      case 'node_load': return <HardDrive size={20} color="#f472b6" />;
      default: return <Database size={20} color="#94a3b8" />;
    }
  };

  const getStatusBadge = (status) => {
    const classMap = {
      idle: 'status-idle',
      running: 'status-running',
      failed: 'status-failed',
      healing: 'status-healing anim-healing',
      patching: 'status-patching',
      verified: 'status-verified anim-verified',
      success: 'status-success'
    };
    return (
      <span className={`status-pill ${classMap[status] || 'status-idle'}`}>
        {status}
      </span>
    );
  };

  return (
    <div className="glass-panel" style={{ padding: '20px', marginBottom: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px' }}>
        <div>
          <h2 style={{ fontSize: '1.05rem', fontWeight: '700', color: '#ffffff' }}>
            Pipeline Execution Graph (Part 1: Planner DAG)
          </h2>
          <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            Real-time node telemetry, error interception hooks, and dynamic hot-patch anchors
          </p>
        </div>
      </div>

      <div style={{ 
        display: 'flex', 
        alignItems: 'center', 
        gap: '12px', 
        overflowX: 'auto', 
        paddingBottom: '10px' 
      }}>
        {nodes.map((node, index) => {
          const isSelected = selectedNodeId === node.id;
          const isFailed = node.status === 'failed';
          const isHealing = node.status === 'healing';
          const isVerified = node.status === 'verified';
          const isSuccess = node.status === 'success';

          let borderStyle = 'var(--border-subtle)';
          let bgStyle = isSelected ? 'rgba(30, 41, 59, 0.9)' : 'rgba(15, 23, 42, 0.65)';
          let boxShadow = 'none';

          if (isFailed) {
            borderStyle = '#f43f5e';
            bgStyle = 'rgba(244, 63, 94, 0.2)';
            boxShadow = '0 0 24px rgba(244, 63, 94, 0.45)';
          } else if (isHealing) {
            borderStyle = '#f59e0b';
            bgStyle = 'rgba(245, 158, 11, 0.2)';
            boxShadow = '0 0 24px rgba(245, 158, 11, 0.45)';
          } else if (isVerified || (isSuccess && node.applied_patch_id)) {
            borderStyle = '#10b981';
            bgStyle = 'rgba(16, 185, 129, 0.18)';
            boxShadow = '0 0 20px rgba(16, 185, 129, 0.35)';
          } else if (isSuccess) {
            borderStyle = 'rgba(16, 185, 129, 0.6)';
            bgStyle = 'rgba(16, 185, 129, 0.1)';
          } else if (isSelected) {
            borderStyle = 'var(--accent-blue)';
          }

          return (
            <React.Fragment key={node.id}>
              <div
                id={`node-card-${node.id}`}
                onClick={() => onSelectNode(node.id)}
                style={{
                  minWidth: '210px',
                  flex: '1 0 210px',
                  padding: '16px 18px',
                  borderRadius: '14px',
                  background: bgStyle,
                  border: `2px solid ${borderStyle}`,
                  cursor: 'pointer',
                  transition: 'all 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
                  boxShadow: boxShadow
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ padding: '6px', borderRadius: '8px', background: 'rgba(255, 255, 255, 0.05)' }}>
                      {getNodeIcon(node.id, node.status)}
                    </div>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: '600' }}>
                      STEP {index + 1}
                    </span>
                  </div>
                  {getStatusBadge(node.status)}
                </div>

                <div style={{ fontSize: '0.85rem', fontWeight: '700', color: '#ffffff', marginBottom: '4px' }}>
                  {node.name.replace(/^\d+\.\s*/, '')}
                </div>

                <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '10px', height: '28px', overflow: 'hidden' }}>
                  {node.description}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid var(--border-subtle)', paddingTop: '8px' }}>
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                    Latency: <strong style={{ color: 'var(--text-secondary)' }}>{node.latency_ms > 0 ? `${node.latency_ms}ms` : '—'}</strong>
                  </span>
                  {node.applied_patch_id && (
                    <span style={{ 
                      fontSize: '0.65rem', 
                      padding: '2px 6px', 
                      borderRadius: '4px', 
                      background: 'rgba(16, 185, 129, 0.15)', 
                      color: '#34d399',
                      border: '1px solid rgba(16, 185, 129, 0.3)',
                      fontWeight: '700'
                    }}>
                      ⚡ PATCHED
                    </span>
                  )}
                </div>
              </div>

              {index < nodes.length - 1 && (
                <div style={{ display: 'flex', alignItems: 'center', color: 'var(--text-muted)' }}>
                  <ArrowRight size={16} />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}
