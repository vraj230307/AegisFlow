import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import confetti from 'canvas-confetti';
import Header from './components/Header';
import MetricsPanel from './components/MetricsPanel';
import PipelineGraph from './components/PipelineGraph';
import FailureControls from './components/FailureControls';
import AgentTerminal from './components/AgentTerminal';
import DataInspector from './components/DataInspector';
import ApiKeyModal from './components/ApiKeyModal';
import BenchmarkSuite from './components/BenchmarkSuite';
import { PipelineWSClient } from './services/websocket';

const BACKEND_BASE = import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";
const WS_URL = import.meta.env.VITE_WS_URL || (BACKEND_BASE.replace(/^http/, 'ws') + "/ws/pipeline");

export default function App() {
  const [activeTab, setActiveTab] = useState('pipeline');
  const [isConnected, setIsConnected] = useState(false);
  const [hasApiKey, setHasApiKey] = useState(false);
  const [isKeyModalOpen, setIsKeyModalOpen] = useState(false);

  const [nodes, setNodes] = useState([]);
  const [selectedNodeId, setSelectedNodeId] = useState('node_cleanse');
  const [selectedScenario, setSelectedScenario] = useState('schema_drift');
  const [useCachedPatches, setUseCachedPatches] = useState(true);
  const [recordsCount, setRecordsCount] = useState(5);
  const [isRunning, setIsRunning] = useState(false);

  const [metrics, setMetrics] = useState({
    total_runs: 0,
    successful_runs: 0,
    healed_runs: 0,
    failed_runs: 0,
    average_mttr_ms: 0,
    active_patches: 0,
    uptime_seconds: 0
  });

  const [logs, setLogs] = useState([]);
  const [latestPatch, setLatestPatch] = useState(null);
  const wsClientRef = useRef(null);

  // Fetch initial plan and metrics from REST API
  useEffect(() => {
    fetch(`${BACKEND_BASE}/api/plan`)
      .then(res => res.json())
      .then(data => {
        if (data.nodes) setNodes(data.nodes);
      })
      .catch(err => console.warn("Failed to load initial plan:", err));

    fetch(`${BACKEND_BASE}/api/metrics`)
      .then(res => res.json())
      .then(data => {
        if (data) setMetrics(data);
      })
      .catch(err => console.warn("Failed to load metrics:", err));

    fetch(`${BACKEND_BASE}/api/health`)
      .then(res => res.json())
      .then(data => {
        if (data) setHasApiKey(data.has_api_key);
      })
      .catch(err => console.warn("Failed to load health:", err));
  }, []);

  // Connect WebSocket
  useEffect(() => {
    const client = new PipelineWSClient(
      WS_URL,
      (eventPayload) => handleWebSocketMessage(eventPayload),
      (status) => setIsConnected(status)
    );
    client.connect();
    wsClientRef.current = client;

    return () => {
      client.disconnect();
    };
  }, []);

  const handleWebSocketMessage = (payload) => {
    const { event, data } = payload;

    switch (event) {
      case 'connected':
        if (data.metrics) setMetrics(data.metrics);
        if (data.has_api_key !== undefined) setHasApiKey(data.has_api_key);
        if (data.patches && data.patches.length > 0) {
          setLatestPatch(data.patches[data.patches.length - 1]);
        }
        addLog("SYSTEM", "Connected to AegisFlow real-time WebSocket telemetry.");
        break;

      case 'pipeline_started':
        setIsRunning(true);
        if (data.nodes) setNodes(data.nodes);
        addLog("INFO", `Pipeline execution initiated (Scenario: ${data.failure_scenario})`);
        break;

      case 'node_status_change':
        setNodes(prev => prev.map(n => n.id === data.id ? { ...n, ...data } : n));
        break;

      case 'error_intercepted':
        addLog("ALERT", `🚨 ERROR INTERCEPTED at ${data.node_id}: ${data.error_type} - ${data.error_message}`);
        break;

      case 'agent_log':
        addLog(data.level || "INFO", data.message);
        break;

      case 'patch_synthesized':
        setLatestPatch(data.patch);
        addLog("PATCH", `⚡ Synthesized Patch '${data.patch.id}' in ${data.repair_time_ms}ms.`);
        break;

      case 'pipeline_completed':
        setIsRunning(false);
        if (data.metrics) setMetrics(data.metrics);
        if (data.was_healed) {
          addLog("SUCCESS", `🎉 Pipeline successfully healed & completed in ${data.duration_ms}ms! All invariants satisfied.`);
          // Trigger celebratory confetti for judges
          try {
            confetti({
              particleCount: 50,
              spread: 60,
              origin: { y: 0.7 }
            });
          } catch (e) {}
        } else {
          addLog("SUCCESS", `Pipeline execution finished cleanly in ${data.duration_ms}ms.`);
        }
        break;

      case 'pipeline_fatal_error':
        setIsRunning(false);
        if (data.metrics) setMetrics(data.metrics);
        addLog("ERROR", `Fatal pipeline error: ${data.error}`);
        break;

      case 'patches_cleared':
        setLatestPatch(null);
        setNodes(prev => prev.map(n => ({ ...n, applied_patch_id: null })));
        setMetrics(prev => ({ ...prev, active_patches: 0 }));
        addLog("WARN", "Purged all in-memory hot-patches. Pipeline will fail on next dirty run.");
        break;

      default:
        break;
    }
  };

  const addLog = (level, message) => {
    setLogs(prev => [...prev.slice(-100), {
      timestamp: Date.now() / 1000,
      level,
      message
    }]);
  };

  const handleRunPipeline = async () => {
    if (isRunning) return;
    setIsRunning(true);

    try {
      const res = await fetch(`${BACKEND_BASE}/api/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          failure_scenario: selectedScenario,
          use_cached_patches: useCachedPatches,
          custom_records_count: recordsCount
        })
      });
      const data = await res.json();
      if (data.nodes) setNodes(data.nodes);
      if (data.metrics) setMetrics(data.metrics);
    } catch (e) {
      addLog("ERROR", `Failed to trigger pipeline run: ${e.message}`);
    } finally {
      setIsRunning(false);
    }
  };

  const handleResetPatches = async () => {
    try {
      await fetch(`${BACKEND_BASE}/api/reset-patches`, { method: 'POST' });
    } catch (e) {
      console.error(e);
    }
  };

  const handleSaveApiKey = async (key) => {
    try {
      const res = await fetch(`${BACKEND_BASE}/api/config/key`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: key })
      });
      const data = await res.json();
      setHasApiKey(data.has_key);
      return data.status === 'success';
    } catch (e) {
      return false;
    }
  };

  const selectedNode = nodes.find(n => n.id === selectedNodeId) || nodes[1] || nodes[0];

  return (
    <div style={{ maxWidth: '1440px', margin: '0 auto', padding: '24px 20px' }}>
      <Header
        isConnected={isConnected}
        onOpenKeyModal={() => setIsKeyModalOpen(true)}
        hasApiKey={hasApiKey}
        activeTab={activeTab}
        onSelectTab={setActiveTab}
      />

      {activeTab === 'benchmark' ? (
        <BenchmarkSuite
          backendUrl={BACKEND_BASE}
          isConnected={isConnected}
        />
      ) : (
        <>
          <MetricsPanel metrics={metrics} />

          <PipelineGraph
            nodes={nodes}
            selectedNodeId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
          />

          <FailureControls
            selectedScenario={selectedScenario}
            onSelectScenario={setSelectedScenario}
            useCachedPatches={useCachedPatches}
            onToggleCachedPatches={setUseCachedPatches}
            recordsCount={recordsCount}
            onChangeRecordsCount={setRecordsCount}
            onRunPipeline={handleRunPipeline}
            onResetPatches={handleResetPatches}
            isRunning={isRunning}
          />

          <AgentTerminal
            logs={logs}
            latestPatch={latestPatch}
          />

          <DataInspector
            selectedNode={selectedNode}
            failureScenario={selectedScenario}
          />
        </>
      )}

      <ApiKeyModal
        isOpen={isKeyModalOpen}
        onClose={() => setIsKeyModalOpen(false)}
        onSaveKey={handleSaveApiKey}
        currentHasKey={hasApiKey}
      />
    </div>
  );
}
