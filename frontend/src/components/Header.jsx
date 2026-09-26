import React from 'react';
import { Shield, Zap, Sparkles, Key, Radio, Terminal } from 'lucide-react';

export default function Header({ isConnected, onOpenKeyModal, hasApiKey, activeTab, onSelectTab }) {
  return (
    <header className="glass-panel" style={{ padding: '16px 24px', marginBottom: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        <div style={{ 
          width: '44px', 
          height: '44px', 
          borderRadius: '12px', 
          background: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 50%, #8b5cf6 100%)',
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          boxShadow: '0 0 20px rgba(59, 130, 246, 0.4)'
        }}>
          <Shield size={24} color="#ffffff" />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h1 id="app-heading" style={{ fontSize: '1.4rem', fontWeight: '800', letterSpacing: '-0.02em', background: 'linear-gradient(90deg, #f1f5f9, #94a3b8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              AegisFlow
            </h1>
            <span style={{ 
              fontSize: '0.7rem', 
              padding: '2px 8px', 
              borderRadius: '6px', 
              background: 'rgba(59, 130, 246, 0.15)', 
              color: '#60a5fa', 
              border: '1px solid rgba(59, 130, 246, 0.3)',
              fontWeight: '600'
            }}>
              HACK-O-OCTO 4.0 • PS01
            </span>
          </div>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            Autonomous Agentic Self-Healing Pipeline Engine with Dynamic Hot-Patching
          </p>
        </div>
      </div>

      {/* Navigation View Switcher */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        background: 'rgba(13, 17, 26, 0.85)',
        padding: '4px',
        borderRadius: '10px',
        border: '1px solid var(--border-subtle)',
        gap: '4px'
      }}>
        <button
          onClick={() => onSelectTab('pipeline')}
          style={{
            padding: '6px 14px',
            borderRadius: '8px',
            fontSize: '0.8rem',
            fontWeight: '600',
            border: 'none',
            cursor: 'pointer',
            background: activeTab === 'pipeline' ? 'rgba(59, 130, 246, 0.25)' : 'transparent',
            color: activeTab === 'pipeline' ? '#60a5fa' : 'var(--text-secondary)',
            boxShadow: activeTab === 'pipeline' ? '0 0 12px rgba(59, 130, 246, 0.2)' : 'none',
            transition: 'all 0.15s ease'
          }}
        >
          Live Pipeline Engine
        </button>

        <button
          onClick={() => onSelectTab('benchmark')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '6px 14px',
            borderRadius: '8px',
            fontSize: '0.8rem',
            fontWeight: '600',
            border: 'none',
            cursor: 'pointer',
            background: activeTab === 'benchmark' ? 'rgba(16, 185, 129, 0.2)' : 'transparent',
            color: activeTab === 'benchmark' ? '#34d399' : 'var(--text-secondary)',
            boxShadow: activeTab === 'benchmark' ? '0 0 12px rgba(16, 185, 129, 0.2)' : 'none',
            transition: 'all 0.15s ease'
          }}
        >
          <span>33-Case Benchmark</span>
          <span style={{
            fontSize: '0.65rem',
            padding: '1px 6px',
            borderRadius: '10px',
            background: '#10b981',
            color: '#022c22',
            fontWeight: '800'
          }}>
            100% SAFE
          </span>
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {/* Gemini Model Badge */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '6px 12px',
          borderRadius: '20px',
          background: 'rgba(139, 92, 246, 0.12)',
          border: '1px solid rgba(139, 92, 246, 0.3)',
          fontSize: '0.75rem',
          color: '#c084fc',
          fontWeight: '600'
        }}>
          <Sparkles size={14} />
          <span>Gemini 2.5 Flash</span>
          {hasApiKey && <span style={{ color: '#10b981', marginLeft: '4px' }}>● Key Active</span>}
        </div>

        {/* Live WS Status */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '6px 12px',
          borderRadius: '20px',
          background: isConnected ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
          border: `1px solid ${isConnected ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
          fontSize: '0.75rem',
          color: isConnected ? '#34d399' : '#fb7185',
          fontWeight: '600'
        }}>
          <Radio size={14} className={isConnected ? "pulse-icon" : "anim-healing"} />
          <span>{isConnected ? "LIVE STREAM" : "RECONNECTING..."}</span>
        </div>

        {/* API Key Modal Button */}
        <button
          id="btn-configure-key"
          className="btn-outline"
          onClick={onOpenKeyModal}
          style={{ fontSize: '0.8rem', padding: '6px 12px' }}
        >
          <Key size={14} />
          <span>API Key</span>
        </button>
      </div>
    </header>
  );
}
