import React, { useState } from 'react';
import DeviceSelector from './components/DeviceSelector';
import LiveView from './components/LiveView';

export default function App() {
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [showAnnotated, setShowAnnotated] = useState(false);

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans select-none">
      {/* Sleek Top Header */}
      <header className="h-16 border-b border-slate-900 bg-slate-950/80 backdrop-blur-md flex items-center justify-between px-8 z-10 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-emerald-500 to-cyan-400 flex items-center justify-center font-bold text-slate-950 text-lg shadow-lg shadow-emerald-500/20">
            F
          </div>
          <div>
            <h1 className="text-lg font-extrabold bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent tracking-tight">
              Fernandes Device Streamer
            </h1>
            <p className="text-[10px] text-slate-500 font-mono tracking-wider uppercase">Android MCP Hub</p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          {/* Annotation Toggle */}
          {selectedDevice && (
            <label className="relative inline-flex items-center cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showAnnotated}
                onChange={(e) => setShowAnnotated(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-slate-800 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-slate-300 after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
              <span className="ml-2 text-xs font-semibold text-slate-400 peer-checked:text-emerald-400 transition-colors">
                Show UI Elements
              </span>
            </label>
          )}

          {/* Status Indicator */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-950/30 border border-emerald-900/40">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider font-mono">
              MCP Server Active
            </span>
          </div>
        </div>
      </header>

      {/* Main Split Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Panel: Device Selector */}
        <aside className="w-80 border-r border-slate-900/80 bg-slate-900/20 backdrop-blur-xs flex flex-col p-6 shrink-0 overflow-y-auto">
          <DeviceSelector
            selectedSerial={selectedDevice}
            onSelectDevice={setSelectedDevice}
          />
          
          {/* ADB Instructions Help Box */}
          <div className="mt-6 p-4 rounded-xl bg-slate-900/30 border border-slate-900 text-[11px] text-slate-500 space-y-2">
            <div className="font-bold text-slate-400 uppercase tracking-wider text-[9px] font-mono">Agent Tooltips</div>
            <p>This server exposes direct ADB device operations to AI agents via the MCP protocol.</p>
            <p>Connect physical devices via USB with USB Debugging enabled, or boot up an emulator from Android Studio.</p>
            <div className="pt-1 font-mono text-slate-600">adb devices</div>
          </div>
        </aside>

        {/* Right Panel: Emulator Live View or Empty State */}
        <main className="flex-1 overflow-y-auto bg-slate-950 relative flex items-center justify-center p-8">
          {selectedDevice ? (
            <div className="w-full h-full flex items-center justify-center animate-fade-in">
              <LiveView
                deviceSerial={selectedDevice}
                showAnnotated={showAnnotated}
              />
            </div>
          ) : (
            <div className="max-w-md text-center space-y-6 animate-fade-in p-8 glass-panel rounded-3xl border border-slate-900/60 shadow-2xl">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-slate-900 to-slate-800 border border-slate-800 flex items-center justify-center mx-auto text-slate-450 shadow-inner">
                <svg className="w-8 h-8 text-slate-550" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
              </div>
              <div className="space-y-2">
                <h3 className="text-lg font-bold text-slate-200">No Device Selected</h3>
                <p className="text-xs text-slate-500 leading-relaxed max-w-xs mx-auto">
                  Select a connected Android device or emulator from the sidebar to stream and control its screen.
                </p>
              </div>
              <div className="text-[10px] text-slate-600 font-mono py-1 px-3 bg-slate-950/40 rounded-lg inline-block border border-slate-900">
                Listening for ADB devices...
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
