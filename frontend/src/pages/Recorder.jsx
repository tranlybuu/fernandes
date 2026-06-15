import React, { useState, useEffect } from 'react';
import LiveView from '../components/LiveView';

export default function Recorder({ selectedDevice, initialName = '', initialGoal = '' }) {
  const [workflowName, setWorkflowName] = useState(initialName);
  const [goal, setGoal] = useState(initialGoal);

  // Prefill values if updated from props (e.g. from Playback Edit click)
  useEffect(() => {
    if (initialName) setWorkflowName(initialName);
    if (initialGoal) setGoal(initialGoal);
  }, [initialName, initialGoal]);
  const [provider, setProvider] = useState('gemini');
  const [modelName, setModelName] = useState('gemini-1.5-flash');
  const [maxSteps, setMaxSteps] = useState(15);
  
  // Status states
  const [status, setStatus] = useState('idle'); // idle, recording, completed, error
  const [logs, setLogs] = useState([]);
  const [currentStep, setCurrentStep] = useState(null);
  const [recordedSteps, setRecordedSteps] = useState([]);
  const [errorMsg, setErrorMsg] = useState('');

  const [backendSettings, setBackendSettings] = useState(null);

  // Load backend settings on mount
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/settings');
        if (res.ok) {
          const data = await res.json();
          setBackendSettings(data);
          if (provider === 'local') {
            setModelName(data.local_llm_model || 'llama3');
          }
        }
      } catch (err) {
        console.error('Failed to load settings in recorder:', err);
      }
    };
    fetchSettings();
  }, []);

  // Update default models when provider changes
  useEffect(() => {
    if (provider === 'openai') {
      setModelName('gpt-4o-mini');
    } else if (provider === 'gemini') {
      setModelName('gemini-1.5-flash');
    } else if (provider === 'anthropic') {
      setModelName('claude-3-5-sonnet-20241022');
    } else if (backendSettings) {
      setModelName(backendSettings.local_llm_model || 'llama3');
    } else {
      setModelName('llama3');
    }
  }, [provider, backendSettings]);

  const startRecording = async (e) => {
    e.preventDefault();
    if (!selectedDevice) {
      alert('Please connect and select a device on the Dashboard first.');
      return;
    }
    if (!workflowName || !goal) {
      alert('Please enter a workflow name and goal.');
      return;
    }

    setStatus('recording');
    setLogs([]);
    setRecordedSteps([]);
    setCurrentStep(null);
    setErrorMsg('');

    const payload = {
      workflow_name: workflowName,
      goal: goal,
      device_serial: selectedDevice,
      llm_provider: provider,
      llm_model: modelName,
      max_steps: parseInt(maxSteps)
    };

    try {
      const response = await fetch('http://localhost:8000/api/record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) throw new Error('Failed to initiate recording');

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
              handleStreamEvent(data);
            } catch (err) {
              console.error('Error parsing stream line:', err);
            }
          }
        }
      }
    } catch (err) {
      setStatus('error');
      setErrorMsg(err.message);
    }
  };

  const handleStreamEvent = (data) => {
    if (data.status === 'starting') {
      setLogs((prev) => [...prev, { type: 'info', text: data.message }]);
    } 
    else if (data.status === 'thinking') {
      setCurrentStep({ num: data.step, thinking: true, details: null });
      setLogs((prev) => [...prev, { type: 'info', text: `Step ${data.step}: LLM is analyzing screen...` }]);
    } 
    else if (data.status === 'decided') {
      setCurrentStep({
        num: data.step,
        thinking: false,
        action: data.action,
        explanation: data.explanation,
        thought: data.thought,
        value: data.value
      });
      setLogs((prev) => [...prev, { 
        type: 'action', 
        text: `Step ${data.step}: Decision: ${data.action.toUpperCase()} - ${data.explanation}` 
      }]);
      
      // Add to recorded steps table
      setRecordedSteps((prev) => [
        ...prev, 
        { step_number: data.step, action: data.action, description: data.explanation, value: data.value }
      ]);
    } 
    else if (data.status === 'completed') {
      setStatus('completed');
      setLogs((prev) => [...prev, { type: 'success', text: data.message }]);
    } 
    else if (data.status === 'saved') {
      setStatus('completed');
      setLogs((prev) => [...prev, { type: 'success', text: `Workflow saved successfully as '${data.workflow.name}'!` }]);
    }
    else if (data.status === 'error') {
      setStatus('error');
      setErrorMsg(data.message);
      setLogs((prev) => [...prev, { type: 'error', text: `Error: ${data.message}` }]);
    }
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-start animate-fade-in">
      {/* Settings Form & Config */}
      <div className="xl:col-span-4 space-y-6">
        <div className="glass-panel rounded-2xl p-6">
          <h3 className="font-bold text-sm text-slate-300 mb-4">Record New Workflow</h3>
          
          <form onSubmit={startRecording} className="space-y-4">
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-400">Workflow Name</label>
              <input
                type="text"
                value={workflowName}
                onChange={(e) => setWorkflowName(e.target.value)}
                placeholder="e.g. open_spotify_and_play"
                disabled={status === 'recording'}
                className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-400">High-Level Goal</label>
              <textarea
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="Describe what the agent should do, e.g. 'Open Calculator app, add 12 plus 45, and verify result is 57'"
                rows={3}
                disabled={status === 'recording'}
                className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 disabled:opacity-50 resize-none"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-400">LLM Provider</label>
                <select
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  disabled={status === 'recording'}
                  className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-3 py-2.5 text-xs text-slate-300 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
                >
                  <option value="gemini">Gemini</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="local">Local API (Ollama)</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-400">Max Steps</label>
                <input
                  type="number"
                  value={maxSteps}
                  onChange={(e) => setMaxSteps(e.target.value)}
                  min={1}
                  max={30}
                  disabled={status === 'recording'}
                  className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-3 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-400">LLM Model Name</label>
              <input
                type="text"
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                disabled={status === 'recording'}
                className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 disabled:opacity-50 font-mono"
              />
            </div>

            <button
              type="submit"
              disabled={status === 'recording' || !selectedDevice}
              className="w-full mt-2 py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 text-xs font-bold transition shadow-lg disabled:opacity-40"
            >
              {status === 'recording' ? 'Recording Loop Running...' : 'Start LLM Recording'}
            </button>

            {!selectedDevice && (
              <p className="text-[10px] text-amber-500 text-center">⚠ Please connect a device in Dashboard first</p>
            )}
          </form>
        </div>

        {/* Live Simulator View */}
        {selectedDevice && (
          <div className="flex justify-center">
            <LiveView deviceSerial={selectedDevice} showAnnotated={status === 'recording'} />
          </div>
        )}
      </div>

      {/* Steps & Live Engine Status */}
      <div className="xl:col-span-8 space-y-6">
        {/* Status Dashboard Panel */}
        <div className="glass-panel rounded-2xl p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="font-bold text-sm text-slate-300">Execution Progress</h3>
            <span className={`text-xs px-3 py-1 rounded-full font-mono font-semibold ${
              status === 'recording' ? 'bg-amber-950/50 text-amber-400 border border-amber-900/50 animate-pulse' :
              status === 'completed' ? 'bg-emerald-950/50 text-emerald-400 border border-emerald-900/50' :
              status === 'error' ? 'bg-red-950/50 text-red-400 border border-red-900/50' :
              'bg-slate-900 text-slate-500 border border-slate-800'
            }`}>
              {status.toUpperCase()}
            </span>
          </div>

          {status === 'idle' && (
            <div className="text-center py-12 text-slate-500">
              <p className="text-xs">Setup a workflow goal and click "Start LLM Recording".</p>
              <p className="text-[10px] text-slate-600 mt-1">The AI agent will analyze the screen layout and execute actions step-by-step.</p>
            </div>
          )}

          {errorMsg && (
            <div className="text-xs text-red-400 bg-red-950/20 border border-red-900/50 rounded-xl p-4 mb-4">
              {errorMsg}
            </div>
          )}

          {/* Current thinking block */}
          {currentStep && (
            <div className="mb-6 bg-slate-900/40 border border-slate-800 rounded-xl p-4 space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-xs font-bold text-emerald-400">Step {currentStep.num} Active Reasoning</span>
                {currentStep.thinking && (
                  <span className="text-[10px] text-slate-500 font-mono animate-pulse">Agent is thinking...</span>
                )}
              </div>
              
              {currentStep.thought && (
                <div className="text-xs bg-slate-950/60 rounded-lg p-3 text-slate-300 border border-slate-900/50">
                  <div className="text-[10px] text-slate-500 uppercase font-mono mb-1">Reasoning</div>
                  {currentStep.thought}
                </div>
              )}

              {currentStep.action && (
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-slate-950/40 p-2.5 rounded-lg border border-slate-900/30">
                    <div className="text-[9px] text-slate-500 font-mono">ACTION TYPE</div>
                    <div className="text-xs font-semibold text-emerald-400 font-mono mt-0.5">{currentStep.action.toUpperCase()}</div>
                  </div>
                  <div className="bg-slate-950/40 p-2.5 rounded-lg border border-slate-900/30">
                    <div className="text-[9px] text-slate-500 font-mono">TARGET ID / VALUE</div>
                    <div className="text-xs font-semibold text-slate-200 font-mono mt-0.5">
                      {currentStep.action === 'click' || currentStep.action === 'input_text' 
                        ? `Element ID: ${currentStep.target_id}` 
                        : `Value: ${currentStep.value || 'N/A'}`}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Table of Recorded Steps */}
          {recordedSteps.length > 0 && (
            <div className="space-y-3 mb-6">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Recorded Steps</h4>
              <div className="overflow-hidden border border-slate-800/80 rounded-xl">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-900/80 border-b border-slate-850 text-slate-400 font-medium">
                      <th className="p-3 w-16 text-center">Step</th>
                      <th className="p-3 w-28">Action</th>
                      <th className="p-3">Description</th>
                      <th className="p-3">Value</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50 bg-slate-900/20">
                    {recordedSteps.map((step, idx) => (
                      <tr key={idx} className="hover:bg-slate-900/30">
                        <td className="p-3 text-center font-mono font-bold text-slate-500">{step.step_number}</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded font-mono text-[10px] font-bold ${
                            step.action === 'click' ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-900/50' :
                            step.action === 'input_text' ? 'bg-blue-950/60 text-blue-400 border border-blue-900/50' :
                            'bg-slate-850 text-slate-400 border border-slate-800'
                          }`}>
                            {step.action}
                          </span>
                        </td>
                        <td className="p-3 text-slate-300">{step.description}</td>
                        <td className="p-3 font-mono text-[11px] text-slate-400 max-w-[120px] truncate">{step.value || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Event Stream Terminal Log */}
          {logs.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">System Action Logs</h4>
              <div className="bg-slate-950 rounded-xl p-4 font-mono text-[11px] text-slate-400 h-64 overflow-y-auto space-y-1.5 border border-slate-900">
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
