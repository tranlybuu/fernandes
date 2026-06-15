import React, { useState, useEffect, useRef } from 'react';

export default function LiveView({ deviceSerial, showAnnotated = false, onElementHover }) {
  const [screenshot, setScreenshot] = useState(null);
  const [elements, setElements] = useState([]);
  const [naturalWidth, setNaturalWidth] = useState(1080); // default fallback
  const [naturalHeight, setNaturalHeight] = useState(1920); // default fallback
  const [loading, setLoading] = useState(false);
  const [inputText, setInputText] = useState('');
  const [inputTextLoading, setInputTextLoading] = useState(false);
  
  const imgRef = useRef(null);
  const intervalRef = useRef(null);

  const fetchScreen = async () => {
    if (!deviceSerial || loading) return;
    setLoading(true);
    try {
      const endpoint = showAnnotated 
        ? `http://localhost:8000/api/annotated-screenshot/${deviceSerial}`
        : `http://localhost:8000/api/screenshot/${deviceSerial}`;
      
      const res = await fetch(endpoint);
      if (!res.ok) throw new Error('Failed to get screenshot');
      const data = await res.json();
      setScreenshot(data.screenshot);
      if (data.elements) {
        setElements(data.elements);
      }
    } catch (err) {
      console.error('Screen fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Poll screen updates
  useEffect(() => {
    fetchScreen();
    // Poll every 800ms for live view feed
    intervalRef.current = setInterval(fetchScreen, 800);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [deviceSerial, showAnnotated]);

  const handleImageLoad = (e) => {
    setNaturalWidth(e.target.naturalWidth);
    setNaturalHeight(e.target.naturalHeight);
  };

  const handleScreenClick = async (e) => {
    if (!imgRef.current || !deviceSerial) return;
    
    const rect = imgRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    
    const scaleX = naturalWidth / rect.width;
    const scaleY = naturalHeight / rect.height;
    
    const actualX = Math.round(clickX * scaleX);
    const actualY = Math.round(clickY * scaleY);
    
    console.log(`Clicking actual screen at (${actualX}, ${actualY})`);

    // Trigger action on backend
    try {
      await fetch('http://localhost:8000/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_serial: deviceSerial,
          action: 'click',
          x: actualX,
          y: actualY
        })
      });
      // Refresh screen immediately after click
      setTimeout(fetchScreen, 500);
    } catch (err) {
      console.error('Click action error:', err);
    }
  };

  const sendSystemKey = async (key) => {
    if (!deviceSerial) return;
    try {
      await fetch('http://localhost:8000/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_serial: deviceSerial,
          action: 'press_key',
          value: key
        })
      });
      setTimeout(fetchScreen, 600);
    } catch (err) {
      console.error('Key action error:', err);
    }
  };

  const sendSwipe = async (dir) => {
    if (!deviceSerial) return;
    try {
      await fetch('http://localhost:8000/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_serial: deviceSerial,
          action: 'swipe',
          value: dir
        })
      });
      setTimeout(fetchScreen, 800);
    } catch (err) {
      console.error('Swipe action error:', err);
    }
  };

  const handleSendText = async (e) => {
    e.preventDefault();
    if (!inputText || !deviceSerial || inputTextLoading) return;
    setInputTextLoading(true);
    try {
      await fetch('http://localhost:8000/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_serial: deviceSerial,
          action: 'input_text',
          value: inputText
        })
      });
      setInputText('');
      setTimeout(fetchScreen, 800);
    } catch (err) {
      console.error('Send text action error:', err);
    } finally {
      setInputTextLoading(false);
    }
  };

  return (
    <div className="glass-card rounded-2xl p-5 flex flex-col items-center w-full max-w-sm">
      <div className="w-full flex justify-between items-center mb-3">
        <span className="text-xs font-semibold text-slate-300">Live Simulator Console</span>
        <button
          onClick={fetchScreen}
          className="text-xs text-slate-500 hover:text-emerald-400 font-mono flex items-center gap-1"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.283 8H18" />
          </svg>
          Refresh Screen
        </button>
      </div>

      {/* Device screen viewport */}
      <div className="relative border-4 border-slate-800 rounded-[2rem] overflow-hidden aspect-[9/16] w-[260px] bg-slate-900 shadow-2xl flex items-center justify-center cursor-pointer select-none">
        {screenshot ? (
          <img
            ref={imgRef}
            src={`data:image/png;base64,${screenshot}`}
            alt="Device screen"
            className="w-full h-full object-contain"
            onLoad={handleImageLoad}
            onClick={handleScreenClick}
          />
        ) : (
          <div className="text-center p-4">
            <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            <p className="text-xs text-slate-500">Connecting live feed...</p>
          </div>
        )}
      </div>

      {/* Navigation Keys */}
      <div className="w-full grid grid-cols-3 gap-2 mt-4">
        <button
          onClick={() => sendSystemKey('back')}
          className="py-2.5 rounded-xl bg-slate-900/60 hover:bg-slate-800 border border-slate-800 text-xs text-slate-400 hover:text-slate-200 transition"
        >
          Back
        </button>
        <button
          onClick={() => sendSystemKey('home')}
          className="py-2.5 rounded-xl bg-slate-900/60 hover:bg-slate-800 border border-slate-800 text-xs text-slate-400 hover:text-slate-200 transition font-bold"
        >
          Home
        </button>
        <button
          onClick={() => sendSystemKey('menu')}
          className="py-2.5 rounded-xl bg-slate-900/60 hover:bg-slate-800 border border-slate-800 text-xs text-slate-400 hover:text-slate-200 transition"
        >
          Apps
        </button>
      </div>

      {/* Swiping controls */}
      <div className="w-full grid grid-cols-4 gap-1.5 mt-2">
        <button
          onClick={() => sendSwipe('up')}
          className="py-1.5 rounded-lg bg-slate-900/40 hover:bg-slate-800/80 border border-slate-800/40 text-[10px] text-slate-400"
        >
          ▲ Up
        </button>
        <button
          onClick={() => sendSwipe('down')}
          className="py-1.5 rounded-lg bg-slate-900/40 hover:bg-slate-800/80 border border-slate-800/40 text-[10px] text-slate-400"
        >
          ▼ Down
        </button>
        <button
          onClick={() => sendSwipe('left')}
          className="py-1.5 rounded-lg bg-slate-900/40 hover:bg-slate-800/80 border border-slate-800/40 text-[10px] text-slate-400"
        >
          ◀ Left
        </button>
        <button
          onClick={() => sendSwipe('right')}
          className="py-1.5 rounded-lg bg-slate-900/40 hover:bg-slate-800/80 border border-slate-800/40 text-[10px] text-slate-400"
        >
          ▶ Right
        </button>
      </div>

      {/* Input Text Form */}
      <form onSubmit={handleSendText} className="w-full mt-4 flex gap-1.5">
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Type text to send..."
          className="flex-1 bg-slate-950/80 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
        />
        <button
          type="submit"
          disabled={inputTextLoading || !inputText}
          className="px-3 rounded-xl bg-emerald-500 text-slate-950 text-xs font-semibold hover:bg-emerald-400 transition disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
