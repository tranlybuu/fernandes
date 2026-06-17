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

  // Intervention state
  const [interventionActive, setInterventionActive] = useState(false);
  const [interventionSession, setInterventionSession] = useState('');
  const [interventionInput, setInterventionInput] = useState('');
  const [sendingIntervention, setSendingIntervention] = useState(false);

  // Test cases state
  const [testCases, setTestCases] = useState([]);
  const [newTestInput, setNewTestInput] = useState('');
  const [addingTest, setAddingTest] = useState(false);
  const [runningTests, setRunningTests] = useState(false);
  const [testResults, setTestResults] = useState([]);
  const [showTestSection, setShowTestSection] = useState(false);

  const [backendSettings, setBackendSettings] = useState(null);

  // Load backend settings on mount
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/settings');
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
        const res = await fetch(`http://127.0.0.1:8000/api/models?provider=${provider}`);
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

  const changeActiveLLM = async (newProvider, newModel) => {
    try {
      const session = (workflowName || '').normalize('NFC');
      const res = await fetch(`http://127.0.0.1:8000/api/session/${encodeURIComponent(session)}/llm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          llm_provider: newProvider,
          llm_model: newModel
        })
      });
      if (!res.ok) {
        console.error('Failed to change active LLM on backend');
      } else {
        const data = await res.json();
        console.log('Active LLM updated on backend:', data.message);
        setLogs(prev => [...prev, { type: 'info', text: `🔄 Model updated mid-run to: ${newProvider} / ${newModel}` }]);
      }
    } catch (err) {
      console.error('Error updating active LLM:', err);
    }
  };

  const handleActiveProviderChange = async (e) => {
    const newProvider = e.target.value;
    setProvider(newProvider);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/models?provider=${newProvider}`);
      if (res.ok) {
        const models = await res.json();
        setAvailableModels(models);
        let defaultModel = models[0];
        if (newProvider === 'openai') {
          defaultModel = models.find(m => m === 'gpt-4o-mini' || m.includes('gpt-4o')) || models[0];
        } else if (newProvider === 'gemini') {
          defaultModel = models.find(m => m === 'gemini-2.5-flash' || m === 'gemini-2.0-flash') || models[0];
        } else if (newProvider === 'anthropic') {
          defaultModel = models.find(m => m.includes('sonnet')) || models[0];
        }
        setModelName(defaultModel);
        if (status === 'recording' || status === 'refining') {
          await changeActiveLLM(newProvider, defaultModel);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleActiveModelChange = async (e) => {
    const newModel = e.target.value;
    setModelName(newModel);
    if (status === 'recording' || status === 'refining') {
      await changeActiveLLM(provider, newModel);
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
      const promptRes = await fetch(`http://127.0.0.1:8000/api/prompts/generate_plan`);
      let initPrompt = '';
      if (promptRes.ok) {
        const promptData = await promptRes.json();
        initPrompt = promptData.content;
        setPromptContent(initPrompt);
      }

      const res = await fetch('http://127.0.0.1:8000/api/plan/generate', {
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
      const res = await fetch('http://127.0.0.1:8000/api/plan/refine', {
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
      const response = await fetch('http://127.0.0.1:8000/api/record', {
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
      const res = await fetch('http://127.0.0.1:8000/api/stop', {
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
    else if (data.status === 'needs_intervention') {
      setInterventionActive(true);
      setInterventionSession((data.session_id || workflowName || '').normalize('NFC'));
      setLogs((prev) => [...prev, { type: 'error', text: `⏸ Agent paused: ${data.message}` }]);
    }
    else if (data.status === 'intervention_received') {
      setInterventionActive(false);
      setLogs((prev) => [...prev, { type: 'info', text: `✅ ${data.message}` }]);
    }
    else if (data.status === 'replanning') {
      setLogs((prev) => [...prev, { type: 'info', text: `🔄 Replanning: ${data.message}` }]);
    }
    else if (data.status === 'plan_updated') {
      if (data.plan) setPlan(data.plan);
      setLogs((prev) => [...prev, { type: 'info', text: `📋 Plan updated: ${data.message || ''}` }]);
    }
    else if (data.status === 'step_error') {
      setLogs((prev) => [...prev, { type: 'error', text: `Step ${data.step} error: ${data.message}` }]);
    }
    else {
      if (data.message) {
        const logType = data.status === 'success' || data.status === 'healed' ? 'success' :
                        data.status === 'error' || data.status === 'failed' ? 'error' : 'info';
        setLogs((prev) => [...prev, { type: logType, text: data.message }]);
      }
    }
  };

  const sendIntervention = async (e) => {
    e.preventDefault();
    if (!interventionInput.trim() || sendingIntervention) return;
    const msg = interventionInput.trim();
    setInterventionInput('');
    setSendingIntervention(true);
    const session = (interventionSession || workflowName || '').normalize('NFC');
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/intervention/${encodeURIComponent(session)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg })
      });
      if (res.ok) {
        setLogs((prev) => [...prev, { type: 'user', text: msg }]);
        setInterventionActive(false);
      } else {
        setLogs((prev) => [...prev, { type: 'error', text: 'Failed to send guidance — session may have ended.' }]);
      }
    } catch (err) {
      setLogs((prev) => [...prev, { type: 'error', text: `Intervention error: ${err.message}` }]);
    } finally {
      setSendingIntervention(false);
    }
  };

  const addTestCase = async () => {
    if (!newTestInput.trim() || !workflowName) return;
    setAddingTest(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/workflows/${encodeURIComponent(workflowName)}/test-cases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newTestInput.trim().slice(0, 60),
          description: newTestInput.trim(),
          check_type: 'llm_assert'
        })
      });
      if (res.ok) {
        const tc = await res.json();
        setTestCases((prev) => [...prev, tc]);
        setNewTestInput('');
      }
    } catch (err) {
      console.error('Add test case error:', err);
    } finally {
      setAddingTest(false);
    }
  };

  const deleteTestCase = async (tcId) => {
    try {
      await fetch(`http://127.0.0.1:8000/api/workflows/${encodeURIComponent(workflowName)}/test-cases/${tcId}`, { method: 'DELETE' });
      setTestCases((prev) => prev.filter((tc) => tc.id !== tcId));
    } catch (err) {
      console.error('Delete test case error:', err);
    }
  };

  const runTestCases = async () => {
    if (!selectedDevice || runningTests || testCases.length === 0) return;
    setRunningTests(true);
    setTestResults([]);
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/workflows/${encodeURIComponent(workflowName)}/run-tests`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_serial: selectedDevice, llm_provider: provider, llm_model: modelName })
      });
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.substring(6));
              if (data.status === 'test_result') {
                setTestResults((prev) => [...prev, data]);
              }
            } catch (_) {}
          }
        }
      }
    } catch (err) {
      console.error('Run tests error:', err);
    } finally {
      setRunningTests(false);
    }
  };

  // Load test cases when workflow is saved/completed
  useEffect(() => {
    if (status === 'completed' && workflowName) {
      fetch(`http://127.0.0.1:8000/api/workflows/${encodeURIComponent(workflowName)}/test-cases`)
        .then((r) => r.ok ? r.json() : [])
        .then((tcs) => { setTestCases(tcs); setShowTestSection(true); })
        .catch(() => {});
    }
  }, [status, workflowName]);

  const [editingStepIdx, setEditingStepIdx] = useState(null);
  const [editingStepData, setEditingStepData] = useState(null);

  const [newStepAction, setNewStepAction] = useState('click');
  const [newStepValue, setNewStepValue] = useState('');
  const [newStepDescription, setNewStepDescription] = useState('');
  const [newStepSelector, setNewStepSelector] = useState('');
  const [showAddStepForm, setShowAddStepForm] = useState(false);

  const saveUpdatedSteps = async (updatedSteps) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/workflows/${encodeURIComponent(workflowName)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ steps: updatedSteps })
      });
      if (res.ok) {
        setRecordedSteps(updatedSteps);
        setEditingStepIdx(null);
        setEditingStepData(null);
      } else {
        alert('Failed to save updated steps to backend');
      }
    } catch (err) {
      console.error(err);
      alert('Error saving steps: ' + err.message);
    }
  };

  const handleEditStepClick = (idx, step) => {
    setEditingStepIdx(idx);
    setEditingStepData({ ...step });
  };

  const handleSaveStepClick = () => {
    if (!editingStepData) return;
    const updated = [...recordedSteps];
    updated[editingStepIdx] = editingStepData;
    saveUpdatedSteps(updated);
  };

  const handleDeleteStepClick = (idx) => {
    if (!window.confirm('Are you sure you want to delete this step?')) return;
    const updated = recordedSteps.filter((_, i) => i !== idx);
    const reindexed = updated.map((step, i) => ({ ...step, step_number: i + 1 }));
    saveUpdatedSteps(reindexed);
  };

  const handleAddStepSubmit = (e) => {
    e.preventDefault();
    let selectorObj = null;
    if (newStepSelector.trim()) {
      try {
        selectorObj = JSON.parse(newStepSelector);
      } catch (_) {
        selectorObj = newStepSelector;
      }
    }
    const newStep = {
      step_number: recordedSteps.length + 1,
      action: newStepAction,
      value: newStepValue || null,
      description: newStepDescription,
      selector: selectorObj
    };
    const updated = [...recordedSteps, newStep];
    saveUpdatedSteps(updated);
    
    setNewStepAction('click');
    setNewStepValue('');
    setNewStepDescription('');
    setNewStepSelector('');
    setShowAddStepForm(false);
  };

  const chatEndRef = React.useRef(null);
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  if (status === 'recording' || status === 'refining') {
    return (
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-start animate-fade-in">
        <div className="xl:col-span-4 space-y-6">
          <div className="glass-panel rounded-2xl p-5 space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-slate-800">
              <h3 className="font-bold text-xs text-slate-400 uppercase tracking-wider">Active Recording</h3>
              <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30 animate-pulse font-mono font-semibold uppercase">
                {status}
              </span>
            </div>

            <div className="space-y-2 text-xs font-mono text-slate-300">
              <div className="truncate"><span className="text-slate-500">Name:</span> {workflowName}</div>
              <div className="line-clamp-2 leading-relaxed"><span className="text-slate-500">Goal:</span> {goal}</div>
              <div><span className="text-slate-500">Model:</span> {modelName}</div>
            </div>

            <button
              type="button"
              onClick={stopWorkflow}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 text-slate-100 text-xs font-bold transition shadow-lg flex items-center justify-center gap-2"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
              </svg>
              Stop Recording
            </button>
          </div>

          <div className="glass-panel rounded-2xl p-5 flex flex-col h-[480px]">
            <div className="flex justify-between items-center pb-2 border-b border-slate-800 mb-4">
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-xs text-slate-400 uppercase tracking-wider">Guidance Chatbox</h3>
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
              </div>
              
              <div className="flex items-center gap-1 text-[10px]">
                <select
                  value={provider}
                  onChange={handleActiveProviderChange}
                  className="bg-transparent border-0 text-slate-500 hover:text-slate-300 text-[10px] focus:outline-none cursor-pointer pr-1 py-0"
                >
                  <option value="gemini" className="bg-slate-950 text-slate-300">Gemini</option>
                  <option value="openai" className="bg-slate-950 text-slate-300">OpenAI</option>
                  <option value="anthropic" className="bg-slate-950 text-slate-300">Anthropic</option>
                  <option value="local" className="bg-slate-950 text-slate-300">Local</option>
                </select>
                <span className="text-slate-700">/</span>
                <select
                  value={modelName}
                  onChange={handleActiveModelChange}
                  className="bg-transparent border-0 text-slate-500 hover:text-slate-300 text-[10px] focus:outline-none max-w-[90px] truncate cursor-pointer py-0"
                >
                  {availableModels.map((m) => (
                    <option key={m} value={m} className="bg-slate-950 text-slate-300">{m}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3.5 pr-1 text-xs scrollbar-thin">
              {logs.map((log, idx) => {
                if (log.type === 'user') {
                  return (
                    <div key={idx} className="flex flex-col items-end">
                      <span className="text-[9px] text-slate-500 mb-0.5 font-mono">User Guidance</span>
                      <div className="max-w-[85%] rounded-2xl px-3.5 py-2.5 bg-emerald-600 text-slate-100 rounded-tr-none font-medium shadow-md shadow-emerald-950/20">
                        {log.text}
                      </div>
                    </div>
                  );
                } else if (log.type === 'action') {
                  return (
                    <div key={idx} className="flex flex-col items-start">
                      <span className="text-[9px] text-emerald-400 mb-0.5 font-mono">Agent Action</span>
                      <div className="max-w-[85%] rounded-2xl px-3.5 py-2.5 bg-slate-900 border border-slate-800/80 text-slate-300 rounded-tl-none font-mono">
                        {log.text}
                      </div>
                    </div>
                  );
                } else if (log.type === 'success') {
                  return (
                    <div key={idx} className="flex flex-col items-start">
                      <span className="text-[9px] text-cyan-400 mb-0.5 font-mono">Agent Status</span>
                      <div className="max-w-[85%] rounded-2xl px-3.5 py-2.5 bg-slate-900 border border-cyan-950/30 text-cyan-300 rounded-tl-none font-semibold">
                        ✓ {log.text}
                      </div>
                    </div>
                  );
                } else if (log.type === 'error') {
                  return (
                    <div key={idx} className="flex flex-col items-start">
                      <span className="text-[9px] text-rose-400 mb-0.5 font-mono">Warning / Error</span>
                      <div className="max-w-[85%] rounded-2xl px-3.5 py-2.5 bg-rose-950/25 border border-rose-900 text-rose-300 rounded-tl-none font-medium">
                        ⚠️ {log.text}
                      </div>
                    </div>
                  );
                } else {
                  return (
                    <div key={idx} className="text-center py-1 font-mono text-[10px] text-slate-500 italic max-w-xs mx-auto">
                      {log.text}
                    </div>
                  );
                }
              })}
              <div ref={chatEndRef} />
            </div>

            <form onSubmit={sendIntervention} className="flex gap-2 mt-4 pt-4 border-t border-slate-800">
              <input
                type="text"
                value={interventionInput}
                onChange={(e) => setInterventionInput(e.target.value.normalize('NFC'))}
                placeholder="Type guidance instruction to send..."
                disabled={sendingIntervention}
                className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 font-sans"
              />
              <button
                type="submit"
                disabled={sendingIntervention || !interventionInput.trim()}
                className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 text-xs font-bold hover:opacity-90 transition disabled:opacity-40"
              >
                Send
              </button>
            </form>
          </div>
        </div>

        <div className="xl:col-span-4 flex justify-center">
          {selectedDevice && (
            <LiveView deviceSerial={selectedDevice} showAnnotated={true} />
          )}
        </div>

        <div className="xl:col-span-4 space-y-6">
          {currentStep && (
            <div className="glass-panel rounded-2xl p-5 space-y-3.5">
              <div className="flex justify-between items-center pb-2 border-b border-slate-800">
                <span className="text-xs font-bold text-emerald-400 font-mono uppercase tracking-wider">Step {currentStep.num} Active Reasoning</span>
                {currentStep.thinking && (
                  <span className="text-[10px] text-slate-500 font-mono animate-pulse">thinking...</span>
                )}
              </div>
              {currentStep.evaluation && (
                <div className="text-xs bg-blue-950/20 rounded-lg p-3 border border-blue-900/20">
                  <div className="text-[9px] text-blue-400 uppercase font-mono mb-1">↩ Evaluation</div>
                  <span className="text-slate-300 leading-relaxed">{currentStep.evaluation}</span>
                </div>
              )}
              {currentStep.next_goal && (
                <div className="text-xs bg-emerald-950/15 rounded-lg p-3 border border-emerald-900/20">
                  <div className="text-[9px] text-emerald-400 uppercase font-mono mb-1">🎯 Next Goal</div>
                  <span className="text-slate-300 leading-relaxed">{currentStep.next_goal}</span>
                </div>
              )}
              {currentStep.thought && (
                <div className="text-xs bg-slate-950/40 rounded-lg p-3 text-slate-300 border border-slate-900/30">
                  <div className="text-[9px] text-slate-500 uppercase font-mono mb-1">Reasoning</div>
                  <p className="leading-relaxed font-sans">{currentStep.thought}</p>
                </div>
              )}
              {currentStep.action && (
                <div className="grid grid-cols-2 gap-3 font-mono text-[11px]">
                  <div className="bg-slate-950/40 p-2.5 rounded-lg border border-slate-900/30">
                    <div className="text-[8px] text-slate-500 uppercase">ACTION TYPE</div>
                    <div className="text-emerald-400 mt-0.5 font-bold">{currentStep.action.toUpperCase()}</div>
                  </div>
                  <div className="bg-slate-950/40 p-2.5 rounded-lg border border-slate-900/30">
                    <div className="text-[8px] text-slate-500 uppercase">TARGET / VALUE</div>
                    <div className="text-slate-300 mt-0.5 truncate font-semibold">
                      {currentStep.action === 'click' || currentStep.action === 'input_text'
                        ? `ID: ${currentStep.target_id}`
                        : currentStep.value || 'N/A'}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {plan.length > 0 && (
            <div className="glass-panel rounded-2xl p-5 border border-slate-800 bg-slate-900/10 space-y-3">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">High-Level Plan</h4>
              <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                {plan.map((item, idx) => {
                  const isCompleted = completedPlanIndices.includes(idx);
                  const isCurrent = currentPlanIndex === idx;
                  const isConditional = typeof item === 'object' && item?.type === 'conditional';
                  const label = isConditional ? item.description : item;
                  return (
                    <div
                      key={idx}
                      className={`flex items-start gap-2.5 p-2.5 rounded-xl border text-[11px] transition ${
                        isCurrent ? 'border-emerald-500/60 bg-emerald-500/5' :
                        isCompleted ? 'border-slate-800 bg-slate-950/20 opacity-50' :
                        'border-slate-900 bg-slate-950/10'
                      }`}
                    >
                      <span className="font-mono text-[10px] text-slate-500">{idx + 1}.</span>
                      <span className="text-slate-300 leading-normal">{label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {recordedSteps.length > 0 && (
            <div className="glass-panel rounded-2xl p-5 border border-slate-800 space-y-3">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Recorded Steps</h4>
              <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                {recordedSteps.map((step, idx) => {
                  const stepNum = step.step_number || idx + 1;
                  const isCurrent = activeStep === stepNum;
                  return (
                    <div
                      key={idx}
                      className={`flex items-center gap-3 p-2.5 rounded-xl border text-xs ${
                        isCurrent ? 'border-emerald-500/60 bg-emerald-500/5' : 'border-slate-900 bg-slate-950/10'
                      }`}
                    >
                      <span className="text-[10px] font-mono font-bold bg-slate-900 border border-slate-800 px-1.5 py-0.5 rounded text-slate-400 uppercase">
                        {step.action}
                      </span>
                      <p className="text-slate-300 truncate flex-1">{step.description}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-start animate-fade-in">
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
                        {msg.plan.map((item, idx) => {
                          const isConditional = typeof item === 'object' && item?.type === 'conditional';
                          const label = isConditional ? item.description : item;
                          return (
                            <div key={idx} className="flex items-start gap-1.5 text-[11px] text-slate-300">
                              <span className="text-emerald-400 font-bold">{idx + 1}.</span>
                              <div className="inline-flex items-center gap-1.5 flex-wrap">
                                {isConditional && (
                                  <span className="text-[8px] px-1.5 py-0.5 rounded bg-purple-950/60 text-purple-400 border border-purple-900/50 font-mono uppercase">if/else</span>
                                )}
                                <span>{label}</span>
                              </div>
                            </div>
                          );
                        })}
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

            <button
              type="button"
              onClick={startExecution}
              disabled={plan.length === 0}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 text-xs font-bold hover:opacity-90 transition shadow-lg disabled:opacity-40"
            >
              Process & Start Recording
            </button>

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
        ) : status === 'completed' || status === 'error' ? (
          <div className="glass-panel rounded-2xl p-5 space-y-4">
            <h3 className="font-bold text-sm text-slate-300 pb-2 border-b border-slate-800">Workflow Details</h3>
            <div className="space-y-2 text-xs font-mono text-slate-300">
              <div><span className="text-slate-500">Workflow Name:</span> {workflowName}</div>
              <div className="line-clamp-3 leading-relaxed"><span className="text-slate-500">Goal:</span> {goal}</div>
            </div>
            {selectedDevice && (
              <div className="flex justify-center pt-2">
                <LiveView deviceSerial={selectedDevice} showAnnotated={false} />
              </div>
            )}
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
                  onChange={(e) => setWorkflowName(e.target.value.normalize('NFC'))}
                  placeholder="e.g. open_spotify_and_play"
                  disabled={status === 'recording' || status === 'refining'}
                  className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-400">High-Level Goal</label>
                <textarea
                  value={goal}
                  onChange={(e) => setGoal(e.target.value.normalize('NFC'))}
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

              <button
                type="submit"
                disabled={!selectedDevice}
                className="w-full mt-2 py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 text-xs font-bold transition shadow-lg disabled:opacity-40"
              >
                Start LLM Recording
              </button>

              {!selectedDevice && (
                <p className="text-[10px] text-amber-500 text-center">⚠ Please connect a device in Dashboard first</p>
              )}
            </form>
          </div>
        )}
      </div>

      <div className={status === 'idle' || status === 'planning' ? "xl:col-span-8 flex justify-center items-center" : "xl:col-span-8 space-y-6"}>
        {(status === 'idle' || status === 'planning') ? (
          selectedDevice ? (
            <LiveView deviceSerial={selectedDevice} showAnnotated={false} />
          ) : (
            <div className="flex flex-col items-center justify-center p-6 glass-panel rounded-2xl min-h-[550px] w-full text-center space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center mx-auto text-slate-600 text-lg">📱</div>
              <p className="text-sm font-semibold text-slate-400">No Device Connected</p>
              <p className="text-xs text-slate-500 leading-relaxed">
                Connect an emulator or device in the Dashboard first to start recording workflows.
              </p>
            </div>
          )
        ) : (
          <div className="glass-panel rounded-2xl p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-sm text-slate-300">Execution Progress</h3>
              <span className={`text-xs px-3 py-1 rounded-full font-mono font-semibold ${
                status === 'completed' ? 'bg-emerald-950/50 text-emerald-400 border border-emerald-900/50' :
                status === 'error' ? 'bg-red-950/50 text-red-400 border border-red-900/50' :
                'bg-slate-900 text-slate-500 border border-slate-800'
              }`}>
                {status.toUpperCase()}
              </span>
            </div>

            {errorMsg && (
              <div className="text-xs text-red-400 bg-red-950/20 border border-red-900/50 rounded-xl p-4 mb-4">
                {errorMsg}
              </div>
            )}

            {recordedSteps.length > 0 && (
              <div className="space-y-4 mb-6">
                <div className="flex justify-between items-center">
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Recorded Steps</h4>
                  <span className="text-[10px] text-slate-500 font-mono font-semibold uppercase">
                    Double-click or hover to Edit/Delete
                  </span>
                </div>
                
                <div className="space-y-3.5">
                  {recordedSteps.map((step, idx) => {
                    const stepNum = step.step_number || idx + 1;
                    const isEditing = editingStepIdx === idx;

                    if (isEditing) {
                      return (
                        <div key={idx} className="p-4 rounded-xl border border-emerald-500/50 bg-slate-950/40 space-y-3.5">
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <label className="block text-[9px] text-slate-500 uppercase font-mono mb-1">Action</label>
                              <select
                                value={editingStepData.action}
                                onChange={(e) => setEditingStepData({ ...editingStepData, action: e.target.value })}
                                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-emerald-500 font-mono"
                              >
                                <option value="click">click</option>
                                <option value="input_text">input_text</option>
                                <option value="press_key">press_key</option>
                                <option value="swipe">swipe</option>
                                <option value="open_app">open_app</option>
                              </select>
                            </div>
                            <div>
                              <label className="block text-[9px] text-slate-500 uppercase font-mono mb-1">Value / Key</label>
                              <input
                                type="text"
                                value={editingStepData.value || ''}
                                onChange={(e) => setEditingStepData({ ...editingStepData, value: e.target.value || null })}
                                placeholder="Value or Key code"
                                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
                              />
                            </div>
                          </div>
                          
                          <div>
                            <label className="block text-[9px] text-slate-500 uppercase font-mono mb-1">Description</label>
                            <input
                              type="text"
                              value={editingStepData.description || ''}
                              onChange={(e) => setEditingStepData({ ...editingStepData, description: e.target.value })}
                              placeholder="Step description"
                              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 font-sans"
                            />
                          </div>

                          <div>
                            <label className="block text-[9px] text-slate-500 uppercase font-mono mb-1">Selector (JSON string or text)</label>
                            <input
                              type="text"
                              value={typeof editingStepData.selector === 'object' ? JSON.stringify(editingStepData.selector) : editingStepData.selector || ''}
                              onChange={(e) => {
                                let val = e.target.value;
                                try {
                                  val = JSON.parse(val);
                                } catch (_) {}
                                setEditingStepData({ ...editingStepData, selector: val });
                              }}
                              placeholder="Selector details"
                              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 font-mono"
                            />
                          </div>

                          <div className="flex justify-end gap-2 pt-1">
                            <button
                              type="button"
                              onClick={() => { setEditingStepIdx(null); setEditingStepData(null); }}
                              className="px-3.5 py-1.5 rounded-lg border border-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-900 text-[11px] font-semibold transition"
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              onClick={handleSaveStepClick}
                              className="px-3.5 py-1.5 rounded-lg bg-emerald-500 text-slate-950 hover:bg-emerald-400 text-[11px] font-bold transition"
                            >
                              Save Changes
                            </button>
                          </div>
                        </div>
                      );
                    }

                    return (
                      <div
                        key={idx}
                        className="flex items-center gap-4 p-3.5 rounded-xl border border-slate-800 bg-slate-900/10 hover:border-slate-700/60 transition group"
                      >
                        <div className="flex-shrink-0">
                          <div className="w-5.5 h-5.5 rounded-full bg-emerald-500/20 border border-emerald-500 flex items-center justify-center text-emerald-400 font-bold">
                            ✓
                          </div>
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

                        <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
                          <button
                            type="button"
                            onClick={() => handleEditStepClick(idx, step)}
                            className="text-[11px] text-slate-400 hover:text-emerald-400 font-semibold px-2 py-1 rounded bg-slate-900 border border-slate-800"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteStepClick(idx)}
                            className="text-[11px] text-slate-500 hover:text-red-400 font-semibold px-2 py-1 rounded bg-slate-900 border border-slate-800"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {showAddStepForm ? (
                  <form onSubmit={handleAddStepSubmit} className="p-4 rounded-xl border border-dashed border-slate-800 bg-slate-950/20 space-y-3.5 mt-3">
                    <h5 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Add New Step</h5>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[9px] text-slate-500 uppercase font-mono mb-1">Action</label>
                        <select
                          value={newStepAction}
                          onChange={(e) => setNewStepAction(e.target.value)}
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none"
                        >
                          <option value="click">click</option>
                          <option value="input_text">input_text</option>
                          <option value="press_key">press_key</option>
                          <option value="swipe">swipe</option>
                          <option value="open_app">open_app</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-[9px] text-slate-500 uppercase font-mono mb-1">Value / Key</label>
                        <input
                          type="text"
                          value={newStepValue}
                          onChange={(e) => setNewStepValue(e.target.value)}
                          placeholder="e.g. hello, enter"
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-[9px] text-slate-500 uppercase font-mono mb-1">Description</label>
                      <input
                        type="text"
                        value={newStepDescription}
                        onChange={(e) => setNewStepDescription(e.target.value)}
                        placeholder="e.g. Click search bar"
                        required
                        className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200"
                      />
                    </div>
                    <div>
                      <label className="block text-[9px] text-slate-500 uppercase font-mono mb-1">Selector (optional JSON or text)</label>
                      <input
                        type="text"
                        value={newStepSelector}
                        onChange={(e) => setNewStepSelector(e.target.value)}
                        placeholder='e.g. {"resource_id": "com.android:id/search"}'
                        className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                    <div className="flex justify-end gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => setShowAddStepForm(false)}
                        className="px-3.5 py-1.5 rounded-lg border border-slate-800 text-slate-400 hover:text-slate-200 text-[10px] font-semibold transition"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="px-3.5 py-1.5 rounded-lg bg-emerald-500 text-slate-950 hover:bg-emerald-400 text-[10px] font-bold transition"
                      >
                        Add Step
                      </button>
                    </div>
                  </form>
                ) : (
                  <button
                    type="button"
                    onClick={() => setShowAddStepForm(true)}
                    className="w-full mt-3 py-2.5 rounded-xl border border-dashed border-slate-800 hover:border-emerald-500/30 hover:bg-emerald-950/5 text-slate-400 hover:text-emerald-400 text-xs font-semibold transition flex items-center justify-center gap-1.5"
                  >
                    <span>+ Add Manual Step</span>
                  </button>
                )}
              </div>
            )}

            {showTestSection && workflowName && (
              <div className="glass-panel rounded-2xl p-5 border border-slate-800 space-y-4 mb-6">
                <div className="flex justify-between items-center">
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">✅ Test Cases</h4>
                  <div className="flex gap-2 items-center">
                    {testCases.length > 0 && (
                      <button
                        onClick={runTestCases}
                        disabled={runningTests || !selectedDevice}
                        className="text-[10px] px-3 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 disabled:opacity-40 transition font-mono"
                      >
                        {runningTests ? '⏳ Running...' : '▶ Run Tests'}
                      </button>
                    )}
                    <button
                      onClick={() => setShowTestSection(!showTestSection)}
                      className="text-[10px] text-slate-500 hover:text-slate-300"
                    >
                      {showTestSection ? 'Hide' : 'Show'}
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  {testCases.length === 0 && (
                    <p className="text-[11px] text-slate-600 text-center py-3">No test cases yet. Describe what to verify below.</p>
                  )}
                  {testCases.map((tc) => {
                    const result = testResults.find((r) => r.id === tc.id);
                    return (
                      <div key={tc.id} className={`flex items-start gap-3 p-3 rounded-xl border transition-all ${
                        result?.passed === true ? 'border-emerald-500/40 bg-emerald-950/20' :
                        result?.passed === false ? 'border-red-500/40 bg-red-950/20' :
                        'border-slate-800 bg-slate-900/20'
                      }`}>
                        <div className="flex-shrink-0 mt-0.5">
                          {result?.passed === true ? (
                            <span className="text-emerald-400 text-sm">✓</span>
                          ) : result?.passed === false ? (
                            <span className="text-red-400 text-sm">✗</span>
                          ) : runningTests ? (
                            <div className="w-4 h-4 border-2 border-slate-500 border-t-transparent rounded-full animate-spin"></div>
                          ) : (
                            <span className="text-slate-600 text-sm">○</span>
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs text-slate-300">{tc.description}</p>
                          {result?.reason && (
                            <p className="text-[10px] text-slate-500 mt-1">{result.reason}</p>
                          )}
                        </div>
                        <button
                          onClick={() => deleteTestCase(tc.id)}
                          className="text-[10px] text-slate-700 hover:text-red-400 transition flex-shrink-0"
                          title="Remove"
                        >
                          ✕
                        </button>
                      </div>
                    );
                  })}
                </div>

                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newTestInput}
                    onChange={(e) => setNewTestInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTestCase(); } }}
                    placeholder="Describe what to verify, e.g. 'YouTube search results for Khoa pub are visible'"
                    disabled={addingTest}
                    className="flex-1 bg-slate-950/80 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
                  />
                  <button
                    onClick={addTestCase}
                    disabled={addingTest || !newTestInput.trim()}
                    className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs hover:bg-slate-700 disabled:opacity-40 transition"
                  >
                    {addingTest ? '...' : '+ Add'}
                  </button>
                </div>
              </div>
            )}

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
        )}
      </div>
    </div>
  );
}
