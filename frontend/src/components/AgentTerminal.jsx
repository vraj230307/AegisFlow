import React, { useRef, useEffect } from 'react';
import { Terminal, Cpu, Code2, Sparkles, Copy, Check } from 'lucide-react';

export default function AgentTerminal({ logs, latestPatch, lastError }) {
  const logEndRef = useRef(null);
  const [copied, setCopied] = React.useState(false);

  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  const handleCopyCode = () => {
    if (latestPatch?.python_code) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(latestPatch.python_code).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        }).catch(() => {
          fallbackCopy(latestPatch.python_code);
        });
      } else {
        fallbackCopy(latestPatch.python_code);
      }
    }
  };

  const fallbackCopy = (text) => {
    try {
      const textArea = document.createElement("textarea");
      textArea.value = text;
      textArea.style.position = "fixed";
      textArea.style.opacity = "0";
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      console.warn("Clipboard copy failed", e);
    }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '20px', marginBottom: '24px' }}>
      {/* Terminal Logs */}
      <div className="glass-panel" style={{ padding: '18px', display: 'flex', flexDirection: 'column', height: '360px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Terminal size={16} color="#38bdf8" />
            <h3 style={{ fontSize: '0.85rem', fontWeight: '700', color: '#ffffff' }}>
              Real-time Visible Reasoning Stream (Part 3: Error Interceptor & Agent)
            </h3>
          </div>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
            WebSocket Live Telemetry
          </span>
        </div>

        <div style={{ 
          flex: 1, 
          overflowY: 'auto', 
          background: 'rgba(0, 0, 0, 0.45)', 
          borderRadius: '8px', 
          padding: '12px',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.75rem',
          lineHeight: '1.6'
        }}>
          {logs.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', padding: '10px' }}>
              &gt; AegisFlow agent standing by. Trigger a pipeline execution to observe error interception and real-time reflection...
            </div>
          ) : (
            logs.map((log, idx) => {
              let color = '#94a3b8';
              if (log.level === 'ALERT' || log.level === 'ERROR') color = '#fb7185';
              else if (log.level === 'WARN') color = '#fbbf24';
              else if (log.level === 'SUCCESS') color = '#34d399';
              else if (log.level === 'PATCH') color = '#c084fc';

              return (
                <div key={idx} style={{ marginBottom: '6px', display: 'flex', gap: '8px', wordBreak: 'break-word' }}>
                  <span style={{ color: 'var(--text-muted)', userSelect: 'none' }}>[{new Date(log.timestamp * 1000).toLocaleTimeString()}]</span>
                  <span style={{ color }}>{log.message}</span>
                </div>
              );
            })
          )}
          <div ref={logEndRef} />
        </div>
      </div>

      {/* Synthesized Patch & Code Diff Viewer */}
      <div className="glass-panel" style={{ padding: '18px', display: 'flex', flexDirection: 'column', height: '360px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={16} color="#c084fc" />
            <h3 style={{ fontSize: '0.85rem', fontWeight: '700', color: '#ffffff' }}>
              Gemini Synthesized Python Adapter (Hot-Patch)
            </h3>
          </div>
          {latestPatch && (
            <button
              className="btn-outline"
              onClick={handleCopyCode}
              style={{ fontSize: '0.7rem', padding: '3px 8px' }}
            >
              {copied ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
              <span>{copied ? "Copied" : "Copy Code"}</span>
            </button>
          )}
        </div>

        {latestPatch ? (
          <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
            {/* Diagnosis Banner */}
            <div style={{ 
              background: 'rgba(139, 92, 246, 0.1)', 
              border: '1px solid rgba(139, 92, 246, 0.3)', 
              borderRadius: '8px', 
              padding: '8px 12px', 
              marginBottom: '10px',
              fontSize: '0.75rem'
            }}>
              <div style={{ fontWeight: '700', color: '#c084fc', marginBottom: '2px' }}>
                Diagnosis: {latestPatch.root_cause}
              </div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.7rem' }}>
                {latestPatch.explanation}
              </div>
            </div>

            {/* Code Box */}
            <div style={{ 
              flex: 1, 
              overflowY: 'auto', 
              background: 'rgba(0, 0, 0, 0.6)', 
              borderRadius: '8px', 
              padding: '12px',
              border: '1px solid rgba(255, 255, 255, 0.05)'
            }}>
              <pre style={{ margin: 0, fontSize: '0.72rem', color: '#38bdf8', lineHeight: '1.45' }}>
                <code>{latestPatch.python_code}</code>
              </pre>
            </div>
            
            <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
              <span>Patch ID: <strong style={{ color: '#ffffff' }}>{latestPatch.id}</strong></span>
              <span>Repair Time: <strong style={{ color: '#10b981' }}>{latestPatch.repair_time_ms} ms</strong></span>
            </div>
          </div>
        ) : (
          <div style={{ 
            flex: 1, 
            display: 'flex', 
            flexDirection: 'column', 
            alignItems: 'center', 
            justifyContent: 'center', 
            color: 'var(--text-muted)',
            textAlign: 'center',
            padding: '20px'
          }}>
            <Code2 size={36} color="var(--border-subtle)" style={{ marginBottom: '10px' }} />
            <p style={{ fontSize: '0.8rem', maxWidth: '280px' }}>
              No hot-patches generated yet. Select a failure scenario (e.g., Schema Drift) and click <strong>Execute Pipeline</strong> to witness live code synthesis.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
