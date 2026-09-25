import React from 'react';
import { Activity, Zap, CheckCircle2, Clock, ShieldCheck } from 'lucide-react';

export default function MetricsPanel({ metrics }) {
  const total = metrics?.total_runs || 0;
  const healed = metrics?.healed_runs || 0;
  const successful = metrics?.successful_runs || 0;
  const mttr = metrics?.average_mttr_ms || 0;
  const patches = metrics?.active_patches || 0;

  const recoveryRate = total > 0 ? Math.round(((successful + healed) / total) * 100) : 100;
  const estimatedHoursSaved = (healed * 0.75).toFixed(1);

  const cards = [
    {
      label: "Autonomous Recovery Rate",
      value: `${recoveryRate}%`,
      subtitle: `${healed} pipeline incidents auto-repaired`,
      icon: <ShieldCheck size={20} color="#10b981" />,
      glowColor: "rgba(16, 185, 129, 0.15)",
      borderColor: "rgba(16, 185, 129, 0.3)"
    },
    {
      label: "Mean Time to Repair (MTTR)",
      value: mttr > 0 ? `${mttr} ms` : "Instant (<1s)",
      subtitle: "vs ~45 min human triage time",
      icon: <Clock size={20} color="#06b6d4" />,
      glowColor: "rgba(6, 182, 212, 0.15)",
      borderColor: "rgba(6, 182, 212, 0.3)"
    },
    {
      label: "Active In-Memory Patches",
      value: patches,
      subtitle: "Zero-latency hot-loaded adapters",
      icon: <Zap size={20} color="#8b5cf6" />,
      glowColor: "rgba(139, 92, 246, 0.15)",
      borderColor: "rgba(139, 92, 246, 0.3)"
    },
    {
      label: "Engineer Time Saved",
      value: `${estimatedHoursSaved} hrs`,
      subtitle: "Midnight pager alerts avoided",
      icon: <CheckCircle2 size={20} color="#f59e0b" />,
      glowColor: "rgba(245, 158, 11, 0.15)",
      borderColor: "rgba(245, 158, 11, 0.3)"
    }
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '24px' }}>
      {cards.map((card, idx) => (
        <div 
          key={idx} 
          className="glass-panel"
          style={{ 
            padding: '16px 20px', 
            background: `linear-gradient(135deg, ${card.glowColor} 0%, rgba(18, 24, 38, 0.8) 100%)`,
            borderColor: card.borderColor
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: '500' }}>
              {card.label}
            </span>
            <div style={{ padding: '6px', borderRadius: '8px', background: 'rgba(255, 255, 255, 0.05)' }}>
              {card.icon}
            </div>
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: '800', color: '#ffffff', letterSpacing: '-0.02em', marginBottom: '4px' }}>
            {card.value}
          </div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            {card.subtitle}
          </div>
        </div>
      ))}
    </div>
  );
}
