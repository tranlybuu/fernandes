import React, { useState } from 'react';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Recorder from './pages/Recorder';
import Playback from './pages/Playback';
import Settings from './pages/Settings';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [playbackWorkflow, setPlaybackWorkflow] = useState(null);
  
  // States for prefilling Recorder when editing
  const [recorderInitialName, setRecorderInitialName] = useState('');
  const [recorderInitialGoal, setRecorderInitialGoal] = useState('');

  const handlePlayWorkflow = (workflowName) => {
    setPlaybackWorkflow(workflowName);
    setActiveTab('playback');
  };

  const handleClosePlayback = () => {
    setPlaybackWorkflow(null);
    setActiveTab('dashboard');
  };

  const handleEditWorkflow = (name, goal) => {
    // Prefill states and route to recorder tab
    setRecorderInitialName(name.replace(/_/g, ' '));
    setRecorderInitialGoal(goal || '');
    setActiveTab('recorder');
  };

  return (
    <Layout activeTab={activeTab} setActiveTab={setActiveTab} playbackWorkflow={playbackWorkflow}>
      <div className={activeTab === 'dashboard' ? '' : 'hidden'}>
        <Dashboard
          selectedDevice={selectedDevice}
          setSelectedDevice={setSelectedDevice}
          onPlayWorkflow={handlePlayWorkflow}
        />
      </div>
      
      <div className={activeTab === 'recorder' ? '' : 'hidden'}>
        <Recorder
          selectedDevice={selectedDevice}
          initialName={recorderInitialName}
          initialGoal={recorderInitialGoal}
        />
      </div>
      
      <div className={activeTab === 'settings' ? '' : 'hidden'}>
        <Settings />
      </div>
      
      <div className={activeTab === 'playback' ? '' : 'hidden'}>
        {playbackWorkflow && (
          <Playback
            selectedDevice={selectedDevice}
            workflowName={playbackWorkflow}
            onClose={handleClosePlayback}
            onEditWorkflow={handleEditWorkflow}
          />
        )}
      </div>
    </Layout>
  );
}
