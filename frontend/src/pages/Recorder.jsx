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
  const [modelName, setModelName] = useState('gemini-3.1-flash-lite');
  const [maxSteps, setMaxSteps] = useState(15);
  
  // Dynamic model options
  const [availableModels, setAvailableModels] = useState([]);
  const [isCustom, setIsCustom] = useState(false);
  
  // Status states
  const [status, setStatus] = useState('idle'); // idle, recording, completed, error
  const [logs, setLogs] = useState([]);
  const [currentStep, setCurrentStep] = useState(null);
  const [recordedSteps, setRecordedSteps] = useState([]);
  const [errorMsg, setErrorMsg] = useState('');
  const [plan, setPlan] = useState([]);
  const [completedPlanIndices, setCompletedPlanIndices] = useState([]);
  const [currentPlanIndex, setCurrentPlanIndex] = useState(null);
  const [activeStep, setActiveStep] = useState(null);
  const [completedSteps, setCompletedSteps] = useState({});
  const [promptContent, setPromptContent] = useState('');
  const [chatMessages, setChatMessages] = useState([]);
  const [feedbackInput, setFeedbackInput] = useState('');
  const [refineLoading, setRefineLoading] = useState(false);
  const [showPromptEditor, setShowPromptEditor] = useState(false);

  const [backendSettings, setBackendSettings] = useState(null);

  // Load backend settings on mount
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/settings');
        if (res.ok) {
          const data = await res.json();
          setBackendSettings(data);
        }
      } catch (err) {
        console.error('Failed to load settings in recorder:', err);
      }
    };
    fetchSettings();
  }, []);

  // Fetch available models whenever provider or backendSettings change
  useEffect(() => {
    const fetchAvailableModels = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/models?provider=${provider}`);
        if (res.ok) {
          const models = await res.json();
          setAvailableModels(models);
          
          // Determine the default model to select
          let defaultModel = '';
          if (provider === 'openai') {
            defaultModel = models.find(m => m === 'gpt-4o-mini' || m.includes('gpt-4o')) || models[0];
          } else if (provider === 'gemini') {
            defaultModel = models.find(m => m === 'gemini-2.5-flash' || m === 'gemini-3.5-flash' || m === 'gemini-3.1-flash-lite' || m === 'gemini-2.0-flash') || models[0];
          } else if (provider === 'anthropic') {
            defaultModel = models.find(m => m.includes('sonnet')) || models[0];
          } else if (provider === 'local') {
            const savedLocal = backendSettings?.local_llm_model;
            defaultModel = models.find(m => m === savedLocal) || models[0];
          } else {
            defaultModel = models[0];
          }
          
          if (defaultModel) {
            setModelName(defaultModel);
            setIsCustom(false);
          }
        }
      } catch (err) {
        console.error('Failed to fetch models:', err);
      }
    };
    
    fetchAvailableModels();
  }, [provider, backendSettings]);

  const handleModelChange = (val) => {
    if (val === 'custom') {
      setIsCustom(true);
      setModelName('');
    } else {
      setIsCustom(false);
      setModelName(val);
    }
  };

  const startPlanning = async (e) => {
    e.preventDefault();
    if (!selectedDevice) {
      alert('Please connect and select a device on the Dashboard first.');
      return;
    }
    if (!workflowName || !goal) {
      alert('Please enter a workflow name and goal.');
      return;
    }

    setStatus('planning');
    setLogs([]);
    setPlan([]);
    setChatMessages([{ sender: 'system', text: 'Generating initial plan from your goal...' }]);
    setFeedbackInput('');
    setErrorMsg('');
    setPromptContent('');
    setShowPromptEditor(false);

    try {
      // Load initial prompt template content
      const promptRes = await fetch(`http://localhost:8000/api/prompts/generate_plan`);
      let initPrompt = '';
      if (promptRes.ok) {
        const promptData = await promptRes.json();
        initPrompt = promptData.content;
        setPromptContent(initPrompt);
      }

      const res = await fetch('http://localhost:8000/api/plan/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: goal,
          llm_provider: provider,
          llm_model: modelName,
          prompt: initPrompt || undefined
        })
      });

      if (!res.ok) throw new Error('Failed to generate initial plan');
      const data = await res.json();
      
      setPlan(data.plan || []);
      setChatMessages(prev => [
        ...prev,
        { 
          sender: 'ai', 
          text: 'I have analyzed the goal and generated this high-level plan. Please review it. You can suggest modifications below or change settings at the bottom.',
          plan: data.plan 
        }
      ]);
    } catch (err) {
      setStatus('error');
      setErrorMsg(err.message);
    }
  };

  const handleRefinePlan = async (e) => {
    e.preventDefault();
    if (!feedbackInput.trim() || refineLoading) return;

    const userMsg = feedbackInput;
    setFeedbackInput('');
    setRefineLoading(true);
    setChatMessages(prev => [...prev, { sender: 'user', text: userMsg }]);

    try {
      const res = await fetch('http://localhost:8000/api/plan/refine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: goal,
          current_plan: plan,
          feedback: userMsg,
          llm_provider: provider,
          llm_model: modelName,
          prompt: promptContent || undefined
        })
      });

      if (!res.ok) throw new Error('Failed to refine plan');
      const data = await res.json();

      if (data.plan) {
        setPlan(data.plan);
      }
      setChatMessages(prev => [
        ...prev,
        { sender: 'ai', text: data.response || 'Plan updated.', plan: data.plan }
      ]);
    } catch (err) {
      setChatMessages(prev => [
        ...prev,
        { sender: 'system', text: `Error refining plan: ${err.message}` }
      ]);
    } finally {
      setRefineLoading(false);
    }
  };

  const startExecution = async () => {
    setStatus('recording');
    setLogs([]);
    setRecordedSteps([]);
    setCurrentStep(null);
    setErrorMsg('');
    setCompletedPlanIndices([]);
    setCurrentPlanIndex(null);
    setActiveStep(null);
    setCompletedSteps({});

    const payload = {
      workflow_name: workflowName,
      goal: goal,
      device_serial: selectedDevice,
      llm_provider: provider,
      llm_model: modelName,
      max_steps: parseInt(maxSteps),
      plan: plan
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

  const stopWorkflow = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_serial: selectedDevice })
      });
      if (res.ok) {
        setLogs(prev => [...prev, { type: 'info', text: 'Stop requested.' }]);
      } else {
        throw new Error('Failed to send stop request');
      }
    } catch (err) {
      console.error('Stop error:', err);
      alert('Error stopping: ' + err.message);
    }
  };

  const handleStreamEvent = (data) => {
    if (data.status === 'starting') {
      setLogs((prev) => [...prev, { type: 'info', text: data.message }]);
      if (data.message && data.message.toLowerCase().includes('verification run')) {
        setStatus('refining');
        setCompletedSteps({});
        setActiveStep(null);
      }
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
    else if (data.status === 'plan_generated') {
      setPlan(data.plan || []);
      setCompletedPlanIndices([]);
      setCurrentPlanIndex(0);
    }
    else if (data.status === 'plan_update') {
      setCompletedPlanIndices(data.completed_indices || []);
      setCurrentPlanIndex(data.current_index);
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
    else if (data.status === 'healed') {
      setCompletedSteps((prev) => ({ ...prev, [data.step]: 'healed' }));
      setLogs((prev) => [...prev, { type: 'success', text: `Step ${data.step}: ${data.message}` }]);
    }
    else if (data.status === 'failed') {
      setCompletedSteps((prev) => ({ ...prev, [data.step]: 'failed' }));
      setLogs((prev) => [...prev, { type: 'error', text: `Step ${data.step} failed: ${data.message}` }]);
    }
    else if (data.status === 'saved') {
      setStatus('completed');
      if (data.workflow && data.workflow.steps) {
        setRecordedSteps(data.workflow.steps);
      }
      setLogs((prev) => [...prev, { type: 'success', text: `Workflow saved successfully as '${data.workflow.name}'!` }]);
    }
    else if (data.status === 'error') {
      setStatus('error');
      setErrorMsg(data.message);
      setLogs((prev) => [...prev, { type: 'error', text: `Error: ${data.message}` }]);
    }
    else {
      if (data.message) {
        const logType = data.status === 'success' || data.status === 'healed' ? 'success' :
                        data.status === 'error' || data.status === 'failed' ? 'error' : 'info';
        setLogs((prev) => [...prev, { type: logType, text: data.message }]);
      }
    }
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-start animate-fade-in">
      {/* Settings Form & Config */}
      <div className="xl:col-span-4 space-y-6">
        {status === 'planning' ? (
          <div className="glass-panel rounded-2xl p-5 space-y-4 flex flex-col h-[600px]">
            <div className="flex justify-between items-center pb-2 border-b border-slate-800">
              <h3 className="font-bold text-sm text-slate-300">Plan Refinement Chat</h3>
              <button 
                type="button"
                onClick={() => setStatus('idle')}
                className="text-[10px] text-slate-500 hover:text-slate-300 px-2 py-1 rounded bg-slate-900 border border-slate-800"
              >
                Cancel
              </button>
            </div>

            {/* Chat Messages Log */}
            <div className="flex-1 overflow-y-auto space-y-3 pr-1 text-xs scrollbar-thin">
              {chatMessages.map((msg, i) => (
                <div key={i} className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                  <div className={`max-w-[90%] rounded-2xl px-3.5 py-2.5 ${
                    msg.sender === 'user' 
                      ? 'bg-emerald-600 text-slate-100 rounded-tr-none' 
                      : msg.sender === 'system' 
                        ? 'bg-slate-900/80 text-slate-500 border border-slate-800/60 italic text-[11px] w-full text-center'
                        : 'bg-slate-850 text-slate-300 rounded-tl-none border border-slate-800/50'
                  }`}>
                    {msg.text}
                    {msg.plan && msg.plan.length > 0 && (
                      <div className="mt-3 space-y-1 bg-slate-950/40 p-2.5 rounded-lg border border-slate-900/50">
                        <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">Proposed Plan:</div>
                        {msg.plan.map((item, idx) => (
                          <div key={idx} className="flex items-start gap-1.5 text-[11px] text-slate-300">
                            <span className="text-emerald-400 font-bold">{idx + 1}.</span>
                            <span>{item}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {refineLoading && (
                <div className="flex items-center gap-2 text-slate-500 italic text-[11px]">
                  <div className="w-3.5 h-3.5 border-2 border-slate-500 border-t-transparent rounded-full animate-spin"></div>
                  Refining plan...
                </div>
              )}
            </div>

            {/* Critique Chat Input */}
            <form onSubmit={handleRefinePlan} className="flex gap-2">
              <input
                type="text"
                value={feedbackInput}
                onChange={(e) => setFeedbackInput(e.target.value)}
                placeholder="Suggest plan adjustments..."
                disabled={refineLoading}
                className="flex-1 bg-slate-950/80 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              />
              <button
                type="submit"
                disabled={refineLoading || !feedbackInput.trim()}
                className="px-3 py-2 rounded-xl bg-emerald-500 text-slate-950 text-xs font-bold hover:bg-emerald-400 disabled:opacity-40 transition"
              >
                Send
              </button>
            </form>

            {/* Process Execution Button */}
            <button
              type="button"
              onClick={startExecution}
              disabled={plan.length === 0}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 text-xs font-bold hover:opacity-90 transition shadow-lg disabled:opacity-40"
            >
              Process & Start Recording
            </button>

            {/* Prompt, Model & Provider Configuration section */}
            <div className="pt-2 border-t border-slate-800 space-y-2.5">
              <div className="flex justify-between items-center">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Advanced Config</span>
                <button 
                  type="button"
                  onClick={() => setShowPromptEditor(!showPromptEditor)}
                  className="text-[10px] text-emerald-400 hover:underline"
                >
                  {showPromptEditor ? 'Hide Prompt' : 'Edit Prompt'}
                </button>
              </div>

              {/* Provider & Model Pickers */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] font-semibold text-slate-500 mb-0.5">Provider</label>
                  <select
                    value={provider}
                    onChange={(e) => setProvider(e.target.value)}
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2 py-1 text-[11px] text-slate-300 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="gemini">Gemini</option>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="local">Local API</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] font-semibold text-slate-500 mb-0.5">Model</label>
                  {isCustom ? (
                    <div className="flex gap-1.5">
                      <input
                        type="text"
                        value={modelName}
                        onChange={(e) => setModelName(e.target.value)}
                        placeholder="Custom model name"
                        className="flex-1 bg-slate-950/80 border border-slate-800 rounded-lg px-2 py-1 text-[11px] text-slate-200 focus:outline-none focus:border-emerald-500 font-mono"
                      />
                      <button
                        type="button"
                        onClick={() => handleModelChange(availableModels[0] || '')}
                        className="text-[10px] text-slate-400 hover:text-slate-200"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <select
                      value={modelName}
                      onChange={(e) => handleModelChange(e.target.value)}
                      className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2 py-1 text-[11px] text-slate-200 focus:outline-none focus:border-emerald-500 font-mono"
                    >
                      {availableModels.map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                      <option value="custom">Custom...</option>
                    </select>
                  )}
                </div>
              </div>

              {/* Prompt Text Editor */}
              {showPromptEditor && (
                <div className="space-y-1">
                  <label className="block text-[10px] font-semibold text-slate-500">System Prompt</label>
                  <textarea
                    value={promptContent}
                    onChange={(e) => setPromptContent(e.target.value)}
                    rows={4}
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-2 py-1.5 text-[10px] text-slate-300 focus:outline-none focus:border-emerald-500 font-mono resize-none"
                  />
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="glass-panel rounded-2xl p-6">
            <h3 className="font-bold text-sm text-slate-300 mb-4">Record New Workflow</h3>
            
            <form onSubmit={startPlanning} className="space-y-4">
              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-400">Workflow Name</label>
                <input
                  type="text"
                  value={workflowName}
                  onChange={(e) => setWorkflowName(e.target.value)}
                  placeholder="e.g. open_spotify_and_play"
                  disabled={status === 'recording' || status === 'refining'}
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
                  disabled={status === 'recording' || status === 'refining'}
                  className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 disabled:opacity-50 resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-slate-400">LLM Provider</label>
                  <select
                    value={provider}
                    onChange={(e) => setProvider(e.target.value)}
                    disabled={status === 'recording' || status === 'refining'}
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
                    disabled={status === 'recording' || status === 'refining'}
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-3 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-400">LLM Model Name</label>
                {isCustom ? (
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={modelName}
                      onChange={(e) => setModelName(e.target.value)}
                      disabled={status === 'recording' || status === 'refining'}
                      placeholder="Enter custom model name"
                      className="flex-1 bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 disabled:opacity-50 font-mono"
                    />
                    <button
                      type="button"
                      disabled={status === 'recording' || status === 'refining'}
                      onClick={() => handleModelChange(availableModels[0] || '')}
                      className="px-3 rounded-xl border border-slate-800 text-xs text-slate-400 hover:text-slate-200 disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <select
                    value={modelName}
                    onChange={(e) => handleModelChange(e.target.value)}
                    disabled={status === 'recording' || status === 'refining'}
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-300 focus:outline-none focus:border-emerald-500 disabled:opacity-50 font-mono"
                  >
                    {availableModels.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                    <option value="custom">Custom...</option>
                  </select>
                )}
              </div>

              {status === 'recording' || status === 'refining' ? (
                <button
                  type="button"
                  onClick={stopWorkflow}
                  className="w-full mt-2 py-3 rounded-xl bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 text-slate-100 text-xs font-bold transition shadow-lg"
                >
                  Stop Recording
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!selectedDevice}
                  className="w-full mt-2 py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 text-xs font-bold transition shadow-lg disabled:opacity-40"
                >
                  Start LLM Recording
                </button>
              )}

              {!selectedDevice && (
                <p className="text-[10px] text-amber-500 text-center">⚠ Please connect a device in Dashboard first</p>
              )}
            </form>
          </div>
        )}

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
              status === 'refining' ? 'bg-cyan-950/50 text-cyan-400 border border-cyan-900/50 animate-pulse' :
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

          {/* High-Level Todo List (Plan) */}
          {plan.length > 0 && (
            <div className="glass-panel rounded-2xl p-5 border border-slate-800 bg-slate-900/10 space-y-3 mb-6">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">High-Level Todo List</h4>
              <div className="space-y-2.5">
                {plan.map((item, idx) => {
                  const isCompleted = completedPlanIndices.includes(idx);
                  const isCurrent = currentPlanIndex === idx;
                  return (
                    <div
                      key={idx}
                      className={`flex items-center gap-3 p-3 rounded-xl border transition-all duration-200 ${
                        isCurrent ? 'border-emerald-500/80 bg-emerald-500/5 shadow shadow-emerald-500/10 scale-[1.005]' :
                        isCompleted ? 'border-slate-800 bg-slate-950/20 opacity-60' :
                        'border-slate-900 bg-slate-950/40'
                      }`}
                    >
                      <div className="flex-shrink-0">
                        {isCompleted ? (
                          <div className="w-5 h-5 rounded-full bg-emerald-500/25 border border-emerald-500 flex items-center justify-center text-emerald-400 font-bold text-xs">
                            ✓
                          </div>
                        ) : isCurrent ? (
                          <div className="w-5 h-5 rounded-full border border-emerald-400 flex items-center justify-center text-emerald-400 animate-spin border-t-transparent"></div>
                        ) : (
                          <div className="w-5 h-5 rounded-full border border-slate-800 flex items-center justify-center text-slate-600 font-bold text-[10px]">
                            {idx + 1}
                          </div>
                        )}
                      </div>
                      <p className={`text-xs ${isCurrent ? 'text-slate-100 font-medium' : isCompleted ? 'text-slate-500 line-through' : 'text-slate-400'}`}>
                        {item}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Recorded Steps Checklist */}
          {recordedSteps.length > 0 && (
            <div className="space-y-3 mb-6">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Recorded Steps</h4>
              <div className="space-y-2">
                {recordedSteps.map((step, idx) => {
                  const stepNum = step.step_number || idx + 1;
                  const isCurrent = activeStep === stepNum;
                  const isSuccess = completedSteps[stepNum] === 'success';
                  const isHealed = completedSteps[stepNum] === 'healed';
                  const isFailed = completedSteps[stepNum] === 'failed';

                  return (
                    <div
                      key={idx}
                      className={`flex items-center gap-4 p-3.5 rounded-xl border transition-all duration-200 ${
                        isCurrent ? 'border-emerald-500/80 bg-emerald-500/10 shadow shadow-emerald-500/20 scale-[1.01]' :
                        isSuccess ? 'border-slate-800 bg-slate-900/10 opacity-70' :
                        isHealed ? 'border-amber-500/40 bg-amber-950/20 shadow shadow-amber-500/5' :
                        isFailed ? 'border-red-500/80 bg-red-500/10 shadow shadow-red-500/10' :
                        'border-slate-900 bg-slate-950/40'
                      }`}
                    >
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
                          <div className="w-5.5 h-5.5 rounded-full bg-emerald-500/25 border border-emerald-500 flex items-center justify-center text-emerald-400 font-bold">
                            ✓
                          </div>
                        )}
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-bold uppercase ${
                            step.action === 'click' ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-900/50' :
                            step.action === 'input_text' ? 'bg-blue-950/60 text-blue-400 border border-blue-900/50' :
                            'bg-slate-850 text-slate-400 border border-slate-805'
                          }`}>
                            {step.action}
                          </span>
                          {step.value && (
                            <span className="text-[10px] text-slate-500 font-mono truncate max-w-[120px]">
                              {step.value}
                            </span>
                          )}
                        </div>
                        <p className="text-xs mt-1 truncate text-slate-300">
                          {step.description}
                        </p>
                      </div>
                    </div>
                  );
                })}
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
