import React from 'react';
import { Play, RotateCcw, AlertOctagon, CheckCircle, Flame, Layers, FileQuestion, Calendar } from 'lucide-react';

export default function FailureControls({
  selectedScenario,
  onSelectScenario,
  useCachedPatches,
  onToggleCachedPatches,
  recordsCount,
  onChangeRecordsCount,
  onRunPipeline,
  onResetPatches,
  isRunning
}) {
  const scenarios = [
    {
      id: "none",
      title: "Clean Baseline",
      desc: "Healthy API payload without schema defects",
      icon: <CheckCircle size={16} color="#10b981" />,
      badge: "Healthy",
      badgeColor: "rgba(16, 185, 129, 0.2)",
      textColor: "#34d399"
    },
    {
      id: "schema_drift",
      title: "Schema Drift (Renamed)",
      desc: "API renamed 'amount' to 'gross_amount' & 'tx_id' to 'reference_id'",
      icon: <Flame size={16} color="#f43f5e" />,
      badge: "Breakage",
      badgeColor: "rgba(244, 63, 94, 0.2)",
      textColor: "#fb7185"
    },
    {
      id: "type_mutation",
      title: "Type Mutation (Symbols)",
      desc: "Prices returned as strings ('$1,250.99 USD') and status as integer",
      icon: <AlertOctagon size={16} color="#f59e0b" />,
      badge: "TypeError",
      badgeColor: "rgba(245, 158, 11, 0.2)",
      textColor: "#fbbf24"
    },
    {
      id: "envelope_relocation",
      title: "Nested API Envelope",
      desc: "API response wrapped inside deep metadata dictionary",
      icon: <Layers size={16} color="#8b5cf6" />,
      badge: "Structure",
      badgeColor: "rgba(139, 92, 246, 0.2)",
      textColor: "#c084fc"
    },
    {
      id: "missing_null_fields",
      title: "Missing & Null Fields",
      desc: "Missing currency codes & null client IDs in records",
      icon: <FileQuestion size={16} color="#06b6d4" />,
      badge: "Nulls",
      badgeColor: "rgba(6, 182, 212, 0.2)",
      textColor: "#38bdf8"
    },
    {
      id: "corrupt_timestamp",
      title: "Corrupt Timestamps",
      desc: "Unix epoch millisecond integers and slash formats",
      icon: <Calendar size={16} color="#ec4899" />,
      badge: "Format",
      badgeColor: "rgba(236, 72, 153, 0.2)",
      textColor: "#f472b6"
    }
  ];

  return (
    <div className="glass-panel" style={{ padding: '20px', marginBottom: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px', marginBottom: '16px' }}>
        <div>
          <h2 style={{ fontSize: '1.05rem', fontWeight: '700', color: '#ffffff' }}>
            Live Failure Injection Station (Judge & Demo Controls)
          </h2>
          <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            Simulate real-world API contract breakages and watch the Gemini agent intercept, diagnose, and hot-patch
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            id="btn-reset-patches"
            className="btn-danger"
            onClick={onResetPatches}
            disabled={isRunning}
            title="Purge in-memory hot patches to demonstrate clean failure and healing"
          >
            <RotateCcw size={14} />
            <span>Purge Hot-Patches</span>
          </button>

          <button
            id="btn-run-pipeline"
            className="btn-primary"
            onClick={onRunPipeline}
            disabled={isRunning}
            style={{ padding: '10px 24px', fontSize: '0.95rem' }}
          >
            <Play size={16} fill="currentColor" />
            <span>{isRunning ? "Executing Pipeline..." : "Execute Pipeline"}</span>
          </button>
        </div>
      </div>

      {/* Scenarios Grid */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', 
        gap: '10px', 
        marginBottom: '16px' 
      }}>
        {scenarios.map((sc) => {
          const isSelected = selectedScenario === sc.id;
          return (
            <div
              key={sc.id}
              id={`scenario-btn-${sc.id}`}
              onClick={() => onSelectScenario(sc.id)}
              style={{
                padding: '12px 14px',
                borderRadius: '10px',
                background: isSelected ? 'rgba(59, 130, 246, 0.18)' : 'rgba(255, 255, 255, 0.03)',
                border: `1.5px solid ${isSelected ? 'var(--accent-blue)' : 'var(--border-subtle)'}`,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                display: 'flex',
                flexDirection: 'column',
                gap: '6px'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {sc.icon}
                  <span style={{ fontSize: '0.82rem', fontWeight: '700', color: isSelected ? '#ffffff' : 'var(--text-primary)' }}>
                    {sc.title}
                  </span>
                </div>
                <span style={{ 
                  fontSize: '0.65rem', 
                  padding: '2px 6px', 
                  borderRadius: '4px', 
                  background: sc.badgeColor, 
                  color: sc.textColor,
                  fontWeight: '600'
                }}>
                  {sc.badge}
                </span>
              </div>
              <p style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', lineHeight: '1.3' }}>
                {sc.desc}
              </p>
            </div>
          );
        })}
      </div>

      {/* Configuration options footer */}
      <div style={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between', 
        flexWrap: 'wrap', 
        gap: '16px',
        paddingTop: '12px',
        borderTop: '1px solid var(--border-subtle)',
        fontSize: '0.8rem',
        color: 'var(--text-secondary)'
      }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
          <input
            id="checkbox-use-cache"
            type="checkbox"
            checked={useCachedPatches}
            onChange={(e) => onToggleCachedPatches(e.target.checked)}
            style={{ accentColor: '#3b82f6', width: '16px', height: '16px' }}
          />
          <span><strong>Use Cached In-Memory Patches</strong> (Enables 0ms zero-latency execution after initial self-healing)</span>
        </label>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>Batch Size:</span>
          <select
            id="select-records-count"
            value={recordsCount}
            onChange={(e) => onChangeRecordsCount(Number(e.target.value))}
            style={{
              background: 'rgba(0, 0, 0, 0.4)',
              border: '1px solid var(--border-subtle)',
              color: '#ffffff',
              padding: '4px 8px',
              borderRadius: '6px',
              fontSize: '0.8rem'
            }}
          >
            <option value={3}>3 Records (Quick)</option>
            <option value={5}>5 Records (Standard)</option>
            <option value={10}>10 Records (Batch)</option>
            <option value={20}>20 Records (High Volume)</option>
          </select>
        </div>
      </div>
    </div>
  );
}
