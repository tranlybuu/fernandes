import React, { useState, useEffect } from 'react';
import DeviceSelector from '../components/DeviceSelector';
import LiveView from '../components/LiveView';

export default function Dashboard({ selectedDevice, setSelectedDevice, onPlayWorkflow }) {
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchWorkflows = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/workflows');
      if (!res.ok) throw new Error('Failed to fetch workflows');
      const data = await res.json();
      setWorkflows(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteWorkflow = async (name) => {
    if (!confirm(`Are you sure you want to delete workflow "${name}"?`)) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/workflows/${name}`, {
        method: 'DELETE'
      });
      if (!res.ok) throw new Error('Failed to delete workflow');
      fetchWorkflows();
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  useEffect(() => {
    fetchWorkflows();
  }, []);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start animate-fade-in">
      {/* Left Column: Device selection and live status */}
      <div className="space-y-6 lg:col-span-1">
        <DeviceSelector 
          selectedSerial={selectedDevice} 
          onSelectDevice={setSelectedDevice} 
        />
        
        {selectedDevice && (
          <LiveView deviceSerial={selectedDevice} showAnnotated={false} />
        )}
      </div>

      {/* Right Column: Workflow library list */}
      <div className="lg:col-span-2 space-y-6">
        <div className="glass-panel rounded-2xl p-6">
          <div className="flex justify-between items-center mb-6">
            <div>
              <h3 className="text-lg font-bold text-slate-100">Workflow Automation Library</h3>
              <p className="text-xs text-slate-500">List of saved LLM-recorded workflows. Run them deterministically without LLMs.</p>
            </div>
            <button
              onClick={fetchWorkflows}
              className="p-2 text-slate-400 hover:text-emerald-400 rounded-lg hover:bg-slate-800/50"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.283 8H18" />
              </svg>
            </button>
          </div>

          {error && (
            <div className="text-xs text-red-400 bg-red-950/20 border border-red-900/50 rounded-xl p-3 mb-4">
              {error}
            </div>
          )}

          {loading ? (
            <div className="text-center py-12">
              <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
              <p className="text-xs text-slate-500">Loading library...</p>
            </div>
          ) : workflows.length === 0 ? (
            <div className="text-center py-12 border-2 border-dashed border-slate-800 rounded-2xl">
              <svg className="w-8 h-8 text-slate-700 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <p className="text-xs text-slate-400">No workflows recorded yet</p>
              <p className="text-[10px] text-slate-600 mt-1">Go to 'Workflow' to create your first automation workflow.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {workflows.map((wfName) => (
                <div
                  key={wfName}
                  className="flex items-center justify-between p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 hover:border-slate-700 transition"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20 text-emerald-400">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                    </div>
                    <div>
                      <div className="font-semibold text-xs text-slate-200">{wfName.replace(/_/g, ' ')}</div>
                      <div className="text-[10px] text-slate-500 font-mono">workflows/{wfName}.json</div>
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={() => onPlayWorkflow(wfName)}
                      disabled={!selectedDevice}
                      className="px-3.5 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-50"
                      title={!selectedDevice ? "Select a device to play" : ""}
                    >
                      <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M8 5v14l11-7z" />
                      </svg>
                      Run Playback
                    </button>
                    <button
                      onClick={() => deleteWorkflow(wfName)}
                      className="p-1.5 rounded-lg border border-slate-800 hover:border-red-500/30 text-slate-500 hover:text-red-400 hover:bg-red-950/10 transition"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
