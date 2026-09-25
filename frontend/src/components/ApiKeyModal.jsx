import React, { useState } from 'react';
import { Key, X, Check, Sparkles, Shield } from 'lucide-react';

export default function ApiKeyModal({ isOpen, onClose, onSaveKey, currentHasKey }) {
  const [keyInput, setKeyInput] = useState('');
  const [statusMsg, setStatusMsg] = useState('');

  if (!isOpen) return null;

  const handleSave = async () => {
    if (!keyInput.trim()) {
      setStatusMsg("Please enter an API key or close the dialog.");
      return;
    }
    const success = await onSaveKey(keyInput.trim());
    if (success) {
      setStatusMsg("API Key successfully updated! Gemini 2.5 Flash is active.");
      setTimeout(() => {
        setStatusMsg('');
        onClose();
      }, 1200);
    } else {
      setStatusMsg("Failed to update API key. Check backend server.");
    }
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.75)',
      backdropFilter: 'blur(8px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: '20px'
    }}>
      <div className="glass-panel" style={{ width: '100%', maxWidth: '480px', padding: '24px', background: '#0e1422', border: '1px solid rgba(255, 255, 255, 0.15)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ padding: '8px', borderRadius: '10px', background: 'rgba(139, 92, 246, 0.2)' }}>
              <Key size={18} color="#c084fc" />
            </div>
            <h3 style={{ fontSize: '1.05rem', fontWeight: '700', color: '#ffffff' }}>
              Google Gemini API Configuration
            </h3>
          </div>
          <button 
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
          >
            <X size={18} />
          </button>
        </div>

        <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '16px', lineHeight: '1.4' }}>
          AegisFlow utilizes <strong>Google Gemini 2.5 Flash</strong> for real-time root-cause reflection and Python patch synthesis.
        </p>

        <div style={{ 
          background: 'rgba(16, 185, 129, 0.1)', 
          border: '1px solid rgba(16, 185, 129, 0.25)', 
          borderRadius: '8px', 
          padding: '10px 14px', 
          marginBottom: '16px',
          fontSize: '0.75rem',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          color: '#34d399'
        }}>
          <Shield size={16} />
          <span>
            {currentHasKey 
              ? "✓ Active Gemini API Key detected. Live LLM reasoning enabled." 
              : "ℹ️ No key set: AegisFlow runs in Resilient Algorithmic Fallback mode (100% demo continuity offline)."}
          </span>
        </div>

        <div style={{ marginBottom: '18px' }}>
          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: '600', color: 'var(--text-secondary)', marginBottom: '6px' }}>
            Gemini API Key
          </label>
          <input
            id="input-gemini-key"
            type="password"
            placeholder="AIzaSy..."
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            style={{
              width: '100%',
              background: 'rgba(0, 0, 0, 0.5)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              padding: '10px 12px',
              color: '#ffffff',
              fontSize: '0.85rem',
              fontFamily: 'var(--font-mono)'
            }}
          />
        </div>

        {statusMsg && (
          <div style={{ fontSize: '0.75rem', marginBottom: '14px', color: statusMsg.includes('success') ? '#34d399' : '#fb7185' }}>
            {statusMsg}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button className="btn-outline" onClick={onClose}>
            Cancel
          </button>
          <button id="btn-save-key" className="btn-primary" onClick={handleSave}>
            <Check size={14} />
            <span>Save Key</span>
          </button>
        </div>
      </div>
    </div>
  );
}
