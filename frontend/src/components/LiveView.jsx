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
  const wsRef = useRef(null);

  // Connect and manage WebSocket stream
  useEffect(() => {
    if (!deviceSerial) return;

    setLoading(true);
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//127.0.0.1:8000/ws/live/${deviceSerial}?showAnnotated=${showAnnotated}`;
    
    console.log("Connecting LiveView WS:", wsUrl);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      setLoading(false);
      try {
        const data = JSON.parse(event.data);
        if (data.error) {
          console.error("WS error payload:", data.error);
          return;
        }
        if (data.screenshot) {
          setScreenshot(data.screenshot);
        }
        if (data.elements) {
          setElements(data.elements);
        }
      } catch (err) {
        console.error("Failed to parse WS screenshot payload:", err);
      }
    };

    ws.onerror = (err) => {
      console.error("WS connection error:", err);
      setLoading(false);
    };

    ws.onclose = () => {
      console.log("WS connection closed");
      setLoading(false);
    };

    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, [deviceSerial, showAnnotated]);

  const triggerWSRefresh = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'refresh', showAnnotated }));
    }
  };

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

    try {
      await fetch('http://127.0.0.1:8000/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_serial: deviceSerial,
          action: 'click',
          x: actualX,
          y: actualY
        })
      });
      // Refresh screen immediately
      setTimeout(triggerWSRefresh, 300);
    } catch (err) {
      console.error('Click action error:', err);
    }
  };

  const sendSystemKey = async (key) => {
    if (!deviceSerial) return;
    try {
      await fetch('http://127.0.0.1:8000/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_serial: deviceSerial,
          action: 'press_key',
          value: key
        })
      });
      setTimeout(triggerWSRefresh, 300);
    } catch (err) {
      console.error('Key action error:', err);
    }
  };

  const sendSwipe = async (dir) => {
    if (!deviceSerial) return;
    try {
      await fetch('http://127.0.0.1:8000/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_serial: deviceSerial,
          action: 'swipe',
          value: dir
        })
      });
      setTimeout(triggerWSRefresh, 400);
    } catch (err) {
      console.error('Swipe action error:', err);
    }
  };

  const handleSendText = async (e) => {
    e.preventDefault();
    if (!inputText || !deviceSerial || inputTextLoading) return;
    setInputTextLoading(true);
    try {
      await fetch('http://127.0.0.1:8000/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_serial: deviceSerial,
          action: 'input_text',
          value: inputText
        })
      });
      setInputText('');
      setTimeout(triggerWSRefresh, 400);
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
          onClick={triggerWSRefresh}
          className="text-xs text-slate-500 hover:text-emerald-400 font-mono flex items-center gap-1 transition"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.283 8H18" />
          </svg>
          Refresh Screen
        </button>
      </div>

      {/* Premium smartphone mockup casing */}
      <div className="relative border-[10px] border-slate-900 rounded-[2.5rem] overflow-hidden aspect-[9/16] w-[260px] bg-slate-950 shadow-2xl flex items-center justify-center cursor-pointer select-none ring-4 ring-slate-800/25">
        
        {/* Smartphone top status notch bar */}
        <div className="absolute top-0 left-0 right-0 h-6 bg-slate-950/70 backdrop-blur-xs z-10 flex justify-between items-center px-4 pointer-events-none text-[8px] font-mono text-slate-400">
          <span>9:41</span>
          <div className="w-12 h-3 bg-slate-950 rounded-full border border-slate-800/40 flex items-center justify-center text-[6px] text-slate-600 font-bold uppercase tracking-wider scale-90">
            notch
          </div>
          <div className="flex items-center gap-1">
            <svg className="w-2 h-2" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 21l-12-12c5-5 19-5 24 0z" />
            </svg>
            <div className="w-3.5 h-2 border border-slate-400 rounded-2xs p-0.5 flex items-center">
              <div className="h-full w-2 bg-emerald-400 rounded-3xs"></div>
            </div>
          </div>
        </div>

        {/* Home bottom indicator pill */}
        <div className="absolute bottom-1.5 left-1/2 -translate-x-1/2 w-20 h-1 bg-slate-700/60 rounded-full z-10 pointer-events-none" />

        {screenshot ? (
          <div className="relative w-full h-full pt-6 pb-2.5 bg-slate-950 flex items-center justify-center">
            <img
              ref={imgRef}
              src={`data:image/png;base64,${screenshot}`}
              alt="Device screen"
              className="w-full h-full object-contain"
              onLoad={handleImageLoad}
              onClick={handleScreenClick}
            />
          </div>
        ) : (
          <div className="text-center p-4">
            <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            <p className="text-xs text-slate-500 font-mono">Connecting Live WS...</p>
          </div>
        )}
      </div>

      {/* Navigation Keys */}
      <div className="w-full grid grid-cols-3 gap-2 mt-4">
        <button
          onClick={() => sendSystemKey('back')}
          className="py-2.5 rounded-xl bg-slate-900/60 hover:bg-slate-800 border border-slate-850 text-xs text-slate-400 hover:text-slate-200 transition"
        >
          Back
        </button>
        <button
          onClick={() => sendSystemKey('home')}
          className="py-2.5 rounded-xl bg-slate-900/60 hover:bg-slate-800 border border-slate-850 text-xs text-slate-400 hover:text-slate-200 transition font-bold"
        >
          Home
        </button>
        <button
          onClick={() => sendSystemKey('menu')}
          className="py-2.5 rounded-xl bg-slate-900/60 hover:bg-slate-800 border border-slate-850 text-xs text-slate-400 hover:text-slate-200 transition"
        >
          Apps
        </button>
      </div>

      {/* Swiping controls */}
      <div className="w-full grid grid-cols-4 gap-1.5 mt-2">
        <button
          onClick={() => sendSwipe('up')}
          className="py-1.5 rounded-lg bg-slate-900/40 hover:bg-slate-850 border border-slate-850/40 text-[10px] text-slate-400 hover:text-slate-300 transition"
        >
          ▲ Up
        </button>
        <button
          onClick={() => sendSwipe('down')}
          className="py-1.5 rounded-lg bg-slate-900/40 hover:bg-slate-850 border border-slate-850/40 text-[10px] text-slate-400 hover:text-slate-300 transition"
        >
          ▼ Down
        </button>
        <button
          onClick={() => sendSwipe('left')}
          className="py-1.5 rounded-lg bg-slate-900/40 hover:bg-slate-850 border border-slate-850/40 text-[10px] text-slate-400 hover:text-slate-300 transition"
        >
          ◀ Left
        </button>
        <button
          onClick={() => sendSwipe('right')}
          className="py-1.5 rounded-lg bg-slate-900/40 hover:bg-slate-850 border border-slate-850/40 text-[10px] text-slate-400 hover:text-slate-300 transition"
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
          className="px-3.5 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
