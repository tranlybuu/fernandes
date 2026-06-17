import React, { useState, useEffect } from 'react';

export default function DeviceSelector({ selectedSerial, onSelectDevice }) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchDevices = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/devices');
      if (!res.ok) throw new Error('Failed to fetch devices');
      const data = await res.json();
      setDevices(data);
      
      // Auto-select first device if none is selected
      if (data.length > 0 && !selectedSerial) {
        onSelectDevice(data[0].serial);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDevices();
  }, []);

  return (
    <div className="glass-card rounded-2xl p-5 w-full">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h3 className="font-semibold text-sm text-slate-300">Android Device Serial</h3>
          <p className="text-xs text-slate-500">Choose connected emulator</p>
        </div>
        <button
          onClick={fetchDevices}
          disabled={loading}
          className="p-2 text-slate-400 hover:text-emerald-400 hover:bg-slate-800/50 rounded-lg transition-all"
          title="Refresh Devices"
        >
          <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.283 8H18" />
          </svg>
        </button>
      </div>

      {error && (
        <div className="text-xs text-red-400 bg-red-950/20 border border-red-900/50 rounded-lg p-3 mb-3">
          Error: {error}
        </div>
      )}

      {devices.length === 0 ? (
        <div className="text-center py-6 border-2 border-dashed border-slate-800 rounded-xl">
          <p className="text-xs text-slate-400 mb-1">No Android devices detected</p>
          <p className="text-[10px] text-slate-600 font-mono">Ensure emulator is running and 'adb devices' lists it.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {devices.map((device) => (
            <button
              key={device.serial}
              onClick={() => onSelectDevice(device.serial)}
              className={`w-full flex items-center justify-between p-3.5 rounded-xl border text-left transition-all ${
                selectedSerial === device.serial
                  ? 'border-emerald-500/50 bg-emerald-500/5 text-slate-200'
                  : 'border-slate-800/80 bg-slate-900/20 text-slate-400 hover:border-slate-700/80 hover:bg-slate-900/40'
              }`}
            >
              <div className="flex items-center gap-3">
                <svg className="w-5 h-5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
                <div>
                  <div className="font-semibold text-xs text-slate-200">{device.model}</div>
                  <div className="text-[10px] text-slate-500 font-mono">{device.serial}</div>
                </div>
              </div>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono ${
                device.status === 'device' ? 'bg-emerald-950/50 text-emerald-400 border border-emerald-900/50' : 'bg-amber-950/50 text-amber-400'
              }`}>
                {device.status}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
