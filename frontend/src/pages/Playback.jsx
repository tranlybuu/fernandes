import React, { useState, useEffect } from 'react';
import LiveView from '../components/LiveView';

export default function Playback({ selectedDevice, workflowName, onClose, onEditWorkflow }) {
  const [workflow, setWorkflow] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  
  // Execution states
  const [status, setStatus] = useState('idle'); // idle, playing, completed, error
  const [activeStep, setActiveStep] = useState(null);
  const [completedSteps, setCompletedSteps] = useState({}); // {step_num: 'success' | 'failed'}
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    fetchWorkflowDetails();
  }, [workflowName]);

  const fetchWorkflowDetails = async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const res = await fetch(`http://localhost:8000/api/workflows/${workflowName}`);
      if (!res.ok) throw new Error('Failed to load workflow details');
      const data = await res.json();
      setWorkflow(data);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  const startPlayback = async () => {
    if (!selectedDevice) {
      alert('Please select a device first.');
      return;
    }
    
    setStatus('playing');
    setLogs([]);
    setActiveStep(null);
    setCompletedSteps({});
    setLogs((prev) => [...prev, { type: 'info', text: `Initiating playback on device ${selectedDevice}...` }]);

    try {
      const response = await fetch('http://localhost:8000/api/playback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workflow_name: workflowName,
          device_serial: selectedDevice
        })
      });

      if (!response.ok) throw new Error('Playback failed to initialize');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop(); // keep last incomplete line

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.substring(6));
              handlePlaybackStreamEvent(data);
            } catch (err) {
              console.error('Error parsing stream line:', err);
            }
          }
        }
      }
    } catch (err) {
      setStatus('error');
      setErrorMsg(err.message);
      setLogs((prev) => [...prev, { type: 'error', text: `Playback error: ${err.message}` }]);
    }
  };

  const handlePlaybackStreamEvent = (data) => {
    if (data.status === 'starting') {
      setLogs((prev) => [...prev, { type: 'info', text: data.message }]);
    }
    else if (data.status === 'executing') {
      setActiveStep(data.step);
      setLogs((prev) => [...prev, { 
        type: 'action', 
        text: `Executing Step ${data.step}: ${data.action.toUpperCase()} - ${data.description}` 
      }]);
    }
    else if (data.status === 'success') {
      setCompletedSteps((prev) => ({ ...prev, [data.step]: 'success' }));
    }
    else if (data.status === 'healing') {
      setLogs((prev) => [...prev, { type: 'info', text: `Step ${data.step}: ${data.message}` }]);
    }
    else if (data.status === 'healing_decision') {
      setLogs((prev) => [...prev, { type: 'action', text: `Step ${data.step}: ${data.message}` }]);
    }
    else if (data.status === 'healed') {
      setCompletedSteps((prev) => ({ ...prev, [data.step]: 'healed' }));
      setLogs((prev) => [...prev, { type: 'success', text: `Step ${data.step}: ${data.message}` }]);
    }
    else if (data.status === 'failed') {
      setCompletedSteps((prev) => ({ ...prev, [data.step]: 'failed' }));
      setStatus('error');
      setLogs((prev) => [...prev, { type: 'error', text: `Step ${data.step} failed: ${data.message}` }]);
    }
    else if (data.status === 'done') {
      setStatus('completed');
      setActiveStep(null);
      setLogs((prev) => [...prev, { type: 'success', text: data.message }]);
    }
    else if (data.status === 'error') {
      setStatus('error');
      setErrorMsg(data.message);
      setLogs((prev) => [...prev, { type: 'error', text: `Error: ${data.message}` }]);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-24 glass-panel rounded-2xl max-w-lg mx-auto">
        <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
        <p className="text-xs text-slate-500 font-mono">Loading workflow steps...</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-start animate-fade-in">
      {/* Left Column: Device Screen and Playback controls */}
      <div className="xl:col-span-4 space-y-6">
        <div className="glass-panel rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <button
              onClick={onClose}
              className="p-1 rounded-lg border border-slate-800 text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div>
              <h3 className="font-bold text-xs text-slate-400 uppercase tracking-wider">Workflow Playback</h3>
              <p className="text-[11px] text-slate-500 font-mono truncate max-w-[180px]">{workflowName}</p>
            </div>
          </div>

          <div className="bg-slate-950/60 rounded-xl p-3 mb-4 border border-slate-900">
            <div className="text-[10px] text-slate-500 font-mono uppercase">Original Goal</div>
            <p className="text-xs text-slate-300 mt-1">{workflow?.goal || 'No goal described.'}</p>
          </div>

          <button
            onClick={startPlayback}
            disabled={status === 'playing' || !selectedDevice}
            className="w-full py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-bold transition shadow-lg shadow-emerald-500/10 flex items-center justify-center gap-2 disabled:opacity-40"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
            {status === 'playing' ? 'Running Automation...' : 'Run Playback'}
          </button>

          <button
            onClick={() => onEditWorkflow && onEditWorkflow(workflowName, workflow?.goal)}
            disabled={status === 'playing'}
            className="w-full mt-3 py-3 rounded-xl border border-slate-800 hover:border-emerald-500/30 hover:bg-emerald-950/10 text-slate-300 hover:text-emerald-400 text-xs font-bold transition flex items-center justify-center gap-2 disabled:opacity-40"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            Edit with LLM
          </button>
        </div>

        {selectedDevice && (
          <div className="flex justify-center">
            {/* During playback, we poll screen updates as well */}
            <LiveView deviceSerial={selectedDevice} showAnnotated={false} />
          </div>
        )}
      </div>

      {/* Right Column: Execution steps checklist */}
      <div className="xl:col-span-8 space-y-6">
        <div className="glass-panel rounded-2xl p-6">
          <div className="flex justify-between items-center mb-6">
            <div>
              <h3 className="text-lg font-bold text-slate-100">Deterministic Execution Engine</h3>
              <p className="text-xs text-slate-500 font-mono">Running saved steps from workflows/{workflowName}.json without LLM calls</p>
            </div>
            <span className={`text-xs px-3 py-1 rounded-full font-mono font-semibold ${
              status === 'playing' ? 'bg-emerald-950/50 text-emerald-400 border border-emerald-900/50 animate-pulse' :
              status === 'completed' ? 'bg-cyan-950/50 text-cyan-400 border border-cyan-900/50' :
              status === 'error' ? 'bg-red-950/50 text-red-400 border border-red-900/50' :
              'bg-slate-900 text-slate-500 border border-slate-800'
            }`}>
              {status.toUpperCase()}
            </span>
          </div>

          {errorMsg && (
            <div className="text-xs text-red-400 bg-red-950/20 border border-red-900/50 rounded-xl p-4 mb-5">
              {errorMsg}
            </div>
          )}

          {/* Workflow Steps Checklist */}
          <div className="space-y-3 mb-6">
            <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Automation Checklist</h4>
            <div className="space-y-2">
              {workflow?.steps.map((step) => {
                const stepNum = step.step_number;
                const isCurrent = activeStep === stepNum;
                const isSuccess = completedSteps[stepNum] === 'success';
                const isHealed = completedSteps[stepNum] === 'healed';
                const isFailed = completedSteps[stepNum] === 'failed';

                return (
                  <div
                    key={stepNum}
                    className={`flex items-center gap-4 p-3.5 rounded-xl border transition-all duration-200 ${
                      isCurrent ? 'border-emerald-500/80 bg-emerald-500/10 shadow shadow-emerald-500/20 scale-[1.01]' :
                      isSuccess ? 'border-slate-800 bg-slate-900/10 opacity-70' :
                      isHealed ? 'border-amber-500/40 bg-amber-950/20 shadow shadow-amber-500/5' :
                      isFailed ? 'border-red-500/80 bg-red-500/10 shadow shadow-red-500/10' :
                      'border-slate-800/80 bg-slate-900/20'
                    }`}
                  >
                    {/* Status Icon */}
                    <div className="flex-shrink-0">
                      {isSuccess ? (
                        <div className="w-5.5 h-5.5 rounded-full bg-emerald-500/25 border border-emerald-500 flex items-center justify-center text-emerald-400 font-bold">
                          ✓
                        </div>
                      ) : isHealed ? (
                        <div className="w-5.5 h-5.5 rounded-full bg-amber-500/20 border border-amber-500/80 flex items-center justify-center text-amber-400 font-bold" title="Self-healed by LLM">
                          ⚡
                        </div>
                      ) : isFailed ? (
                        <div className="w-5.5 h-5.5 rounded-full bg-red-500/25 border border-red-500 flex items-center justify-center text-red-400 font-bold">
                          ✗
                        </div>
                      ) : isCurrent ? (
                        <div className="w-5.5 h-5.5 rounded-full border border-emerald-400 flex items-center justify-center text-emerald-400 animate-spin border-t-transparent"></div>
                      ) : (
                        <div className="w-5.5 h-5.5 rounded-full border border-slate-800 flex items-center justify-center text-slate-600 font-mono text-[10px] font-bold">
                          {stepNum}
                        </div>
                      )}
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-bold uppercase ${
                          step.action === 'click' ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-900/50' :
                          step.action === 'input_text' ? 'bg-blue-950/60 text-blue-400 border border-blue-900/50' :
                          'bg-slate-800 text-slate-400 border border-slate-700'
                        }`}>
                          {step.action}
                        </span>
                        {step.value && (
                          <span className="text-[10px] text-slate-500 font-mono truncate max-w-[120px]">
                            {step.value}
                          </span>
                        )}
                      </div>
                      <p className={`text-xs mt-1 truncate ${isCurrent ? 'text-slate-100 font-medium' : 'text-slate-400'}`}>
                        {step.description}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Terminal logs */}
          {logs.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Playback System Logs</h4>
              <div className="bg-slate-950 rounded-xl p-4 font-mono text-[11px] text-slate-400 h-48 overflow-y-auto space-y-1.5 border border-slate-900">
                {logs.map((log, idx) => (
                  <div key={idx} className={`leading-relaxed ${
                    log.type === 'action' ? 'text-emerald-400/90' :
                    log.type === 'error' ? 'text-red-400' :
                    log.type === 'success' ? 'text-cyan-400 font-bold' :
                    'text-slate-500'
                  }`}>
                    <span className="text-slate-700 mr-2">[{new Date().toLocaleTimeString()}]</span>
                    {log.text}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
