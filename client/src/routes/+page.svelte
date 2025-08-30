<script>
  let recognition;
  let interimTranscript = '';
  let finalTranscript = '';
  let isListening = false;
  let status = 'Tap to Start';
  let conversationHistory = [];

  // Prevent duplicate submits and duplicate audio
  let inFlight = false;
  let audioEl = null;

  // Web Audio API for audio-reactive orb
  let audioCtx;
  let analyser;     // AI playback analyser
  let sourceNode;   // AI playback source
  let dataArray;    // AI spectrum buffer
  let rafId = 0;
  let speaking = false; // AI is speaking
  let orbLevel = 0; // 0..1 intensity for glow/scale

  // Microphone visualisation (react while the user is speaking)
  let micActive = false;
  let micStream;
  let micSource;
  let micAnalyser;
  let micDataArray;

  // Ensure AudioContext exists and is resumed (must be called from a user gesture)
  async function ensureAudioCtx() {
    try {
      if (!audioCtx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        audioCtx = new AC();
      }
      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }
    } catch (e) {
      console.warn('AudioContext resume failed', e);
    }
  }

  async function startMicViz() {
    try {
      await ensureAudioCtx();
      // Ask for mic access only when we need it
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micSource = audioCtx.createMediaStreamSource(micStream);
      micAnalyser = audioCtx.createAnalyser();
      micAnalyser.fftSize = 1024;
      micDataArray = new Uint8Array(micAnalyser.fftSize);
      micSource.connect(micAnalyser);
      micActive = true;
      if (!rafId) rafId = requestAnimationFrame(speakingAnimationLoop);
    } catch (e) {
      console.warn('Microphone visualizer unavailable:', e);
      micActive = false;
    }
  }

  function stopMicViz() {
    micActive = false;
    try {
      if (micSource) micSource.disconnect();
      if (micAnalyser) micAnalyser.disconnect();
      if (micStream) micStream.getTracks().forEach(t => t.stop());
    } catch {}
    micSource = null;
    micAnalyser = null;
    micDataArray = null;
    micStream = null;
    // Don't cancel RAF here; the loop stops itself when both micActive and speaking are false
  }

  // UI state for new design
  let isHistoryOpen = false;

  // Floating subtitles: track just the latest line
  let currentSubtitle = '';
  let previousSubtitle = '';

  // Auto-stop configuration
  const SILENCE_TIMEOUT_MS = 6500; // stop after 6.5s of silence
  const MAX_LISTEN_MS = 30000;     // hard cap: 30s per turn

  let silenceTimer = null;
  let maxListenTimer = null;

  function clearTimers() {
    if (silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
    }
    if (maxListenTimer) {
      clearTimeout(maxListenTimer);
      maxListenTimer = null;
    }
  }

  function armSilenceTimer() {
    if (silenceTimer) clearTimeout(silenceTimer);
    silenceTimer = setTimeout(() => {
      if (isListening && !inFlight) {
        // Trigger stop+process on prolonged silence
        isListening = false;
        handleOrbRelease();
      }
    }, SILENCE_TIMEOUT_MS);
  }

  function armMaxListenTimer() {
    if (maxListenTimer) clearTimeout(maxListenTimer);
    maxListenTimer = setTimeout(() => {
      if (isListening && !inFlight) {
        // Auto-stop after max duration
        isListening = false;
        handleOrbRelease();
      }
    }, MAX_LISTEN_MS);
  }

  function setSubtitleFromHistory() {
    const last = conversationHistory[conversationHistory.length - 1];
    if (!last) return;
    previousSubtitle = currentSubtitle;
    currentSubtitle = last.text || '';
  }

  function toggleHistory() {
    isHistoryOpen = !isHistoryOpen;
  }

  // Resolver used to await recognition.onend when stopping recognition
  let recognitionEndResolver = null;

  // Speaking visualizer helpers
  function stopSpeakingViz() {
    speaking = false;
    try {
      if (analyser) analyser.disconnect();
      if (sourceNode) sourceNode.disconnect();
    } catch {}
    analyser = null;
    sourceNode = null;
    dataArray = null;

    // Only stop the loop if mic is not active either
    if (!micActive && rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
      orbLevel = 0;
    }
  }

  function speakingAnimationLoop() {
    // Read AI playback energy
    let aiLevel = 0;
    if (speaking && analyser && dataArray) {
      analyser.getByteFrequencyData(dataArray);
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
      const avg = sum / (dataArray.length || 1);
      // Slightly more sensitive mapping for stronger pulse
      aiLevel = Math.min(1, Math.max(0, (avg - 10) / 100));
    }

    // Read microphone energy (RMS of time-domain)
    let micLevel = 0;
    if (micActive && micAnalyser) {
      if (!micDataArray) micDataArray = new Uint8Array(micAnalyser.fftSize);
      micAnalyser.getByteTimeDomainData(micDataArray);
      let sumSq = 0;
      for (let i = 0; i < micDataArray.length; i++) {
        const v = (micDataArray[i] - 128) / 128;
        sumSq += v * v;
      }
      const rms = Math.sqrt(sumSq / (micDataArray.length || 1));
      // Map RMS (~0..~0.5) into 0..1 with a small floor
      micLevel = Math.min(1, Math.max(0, (rms - 0.02) / 0.2));
    }

    // Combine signals; emphasize mic slightly to feel responsive while talking
    const combined = Math.max(aiLevel, micLevel * 1.2);
    orbLevel = combined;

    if (speaking || micActive) {
      rafId = requestAnimationFrame(speakingAnimationLoop);
    } else {
      // No sources active; stop loop
      if (rafId) {
        cancelAnimationFrame(rafId);
        rafId = 0;
      }
      orbLevel = 0;
    }
  }

  if (typeof window !== 'undefined') {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onresult = (event) => {
      let tempInterim = '';
      // Do NOT reset finalTranscript here — keep accumulated final text across short pauses.
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        } else {
          tempInterim += event.results[i][0].transcript;
        }
      }
      interimTranscript = tempInterim;

      // Any incoming audio resets the silence timer
      armSilenceTimer();
    };

    recognition.onstart = () => {
      isListening = true;
      status = 'Tap to Stop';
      // Arm timers when listening begins
      armSilenceTimer();
      armMaxListenTimer();
    };

    recognition.onend = () => {
      // Resolve any waiter that is awaiting the recognition end
      try {
        if (recognitionEndResolver) {
          recognitionEndResolver();
          recognitionEndResolver = null;
        }
      } catch (e) {
        console.error('Recognition end resolver error', e);
      }

      // Clear any auto-stop timers
      clearTimers();

      isListening = false;
      if (status === 'Tap to Stop') {
        status = 'Tap to Start';
      }
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error', event.error);
      isListening = false;
      status = 'Tap to Start';
    };
  }

  // Tap-to-toggle handler
  function handleOrbClick() {
    if (inFlight) return;
    if (!isListening) {
      // Start listening
      finalTranscript = '';
      interimTranscript = '';
      isListening = true;
      status = 'Tap to Stop';
      // Prime/resume AudioContext under a click user-gesture to satisfy autoplay policies
      ensureAudioCtx();
      recognition.start();
    } else {
      // Stop and process captured speech
      isListening = false;
      handleOrbRelease();
    }
  }

  async function handleOrbRelease() {
    // Prevent duplicate in-flight requests (allows processing even if recognition.onend already fired)
    if (inFlight) return;
    inFlight = true;

    // Stop timers while we finalize this turn
    clearTimers();

    recognition.stop();
    status = 'Thinking...';

    // Wait for recognition.onend to run so finalTranscript is fully populated.
    try {
      await new Promise((resolve) => {
        let finished = false;
        // Safety timeout in case onend doesn't fire
        const to = setTimeout(() => {
          if (!finished) {
            finished = true;
            recognitionEndResolver = null;
            resolve();
          }
        }, 1000);
        recognitionEndResolver = () => {
          if (!finished) {
            finished = true;
            clearTimeout(to);
            recognitionEndResolver = null;
            resolve();
          }
        };
      });
    } catch (e) {
      // ignore and continue to read finalTranscript
      console.warn('Waiting for recognition end failed:', e);
    }

    const capturedTranscript = finalTranscript.trim();
    if (!capturedTranscript) {
      console.log('No speech detected.');
      status = 'Tap to Start';
      inFlight = false;
      return;
    }

    const userMessage = { role: 'user', text: capturedTranscript };
    conversationHistory = [...conversationHistory, userMessage];
    setSubtitleFromHistory();

    try {
      const response = await fetch('http://localhost:8000/api/conversation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: capturedTranscript, history: conversationHistory })
      });

      if (!response.ok) {
        throw new Error(`Network response was not ok: ${response.statusText}`);
      }

      const data = await response.json();

      // Append model reply only if it's not already the last entry
      const aiMessage = { role: 'model', text: data.text };
      const last = conversationHistory[conversationHistory.length - 1];
      if (!last || last.role !== 'model' || last.text !== data.text) {
        conversationHistory = [...conversationHistory, aiMessage];
      }
      setSubtitleFromHistory();

      // Play audio once: stop any previous playback first
      try {
        if (audioEl) {
          audioEl.pause();
          audioEl.currentTime = 0;
        }
        audioEl = new Audio(`http://localhost:8000${data.audio_url}`);
        audioEl.crossOrigin = 'anonymous';
        audioEl.muted = false;
        audioEl.volume = 1;

        // Initialize Web Audio graph and speaking animation
        await ensureAudioCtx();
        if (sourceNode) {
          try { sourceNode.disconnect(); } catch {}
        }
        sourceNode = audioCtx.createMediaElementSource(audioEl);
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        dataArray = new Uint8Array(analyser.frequencyBinCount);
        // Route audio through analyser to destination
        sourceNode.connect(analyser);
        analyser.connect(audioCtx.destination);

        audioEl.onplay = async () => {
          try {
            if (audioCtx.state === 'suspended') await audioCtx.resume();
          } catch {}
          speaking = true;
          speakingAnimationLoop();
        };
        audioEl.onerror = (e) => {
          console.error('Audio element error', e, audioEl.error);
          stopSpeakingViz();
        };
        const stop = () => { stopSpeakingViz(); };
        audioEl.onpause = stop;
        audioEl.onended = stop;

        await audioEl.play();
      } catch (e) {
        console.error('Error playing audio', e);
      }
    } catch (error) {
      console.error('There was a problem with the fetch operation:', error);
      status = 'Error!';
      conversationHistory = [...conversationHistory, { role: 'system', text: 'Sorry, I encountered an error.' }];
      setSubtitleFromHistory();
    } finally {
      status = 'Tap to Start';
      // Clear transcripts only after we've recorded them into history
      finalTranscript = '';
      interimTranscript = '';
      inFlight = false;
    }
  }

  // Download session summary as a text file
  async function handleDownload() {
    try {
      if (!conversationHistory || conversationHistory.length === 0) return;

      const response = await fetch('http://localhost:8000/api/summary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ history: conversationHistory })
      });

      if (!response.ok) {
        throw new Error(`Network response was not ok: ${response.statusText}`);
      }

      const data = await response.json();
      const text = data.summary_text ?? 'No summary returned.';

      const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);

      const a = document.createElement('a');
      a.href = url;
      a.download = 'kai-session-summary.txt';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Failed to download summary', e);
    }
  }
</script>

<!-- Minimalist, immersive layout -->
<div class="min-h-screen bg-gray-900 text-white font-sans flex flex-col overflow-hidden">
  <!-- Title -->
  <header class="py-6 text-center">
    <h1 class="text-3xl md:text-4xl font-bold">Kai - Your AI NLP Coach</h1>
  </header>

  <!-- Centered Orb and Floating Subtitles -->
  <main class="flex-1 flex flex-col items-center justify-center relative">
    <!-- Orb -->
    <div
      class="orb relative rounded-full w-56 h-56 md:w-72 md:h-72 lg:w-80 lg:h-80 cursor-pointer select-none transition-transform duration-300 ease-in-out bg-gradient-to-br from-purple-600 via-purple-700 to-indigo-700 breathing"
      class:breathing-active={isListening || speaking}
      on:click={handleOrbClick}
      role="button"
      aria-label="Tap to start or stop listening"
      tabindex="0"
      style={`--orb-scale:${(1 + orbLevel * 0.06).toFixed(3)}; --orb-glow:${Math.round(orbLevel * 60)}px;`}
    >
      <!-- Inner label -->
      <div class="absolute inset-0 rounded-full flex items-center justify-center text-white font-semibold">
        {status}
      </div>
      <!-- Soft glow ring -->
      <div class="pointer-events-none absolute -inset-3 rounded-full bg-purple-600/20 blur-2xl"></div>
    </div>

    <!-- Floating Subtitles (recent line only) -->
    <div class="relative mt-6 h-16 w-[90%] max-w-3xl text-center">
      {#if previousSubtitle}
        <p class="subtitle-old text-gray-400 italic">{previousSubtitle}</p>
      {/if}
      {#if currentSubtitle || interimTranscript || finalTranscript}
        <p class="subtitle-new text-gray-200 italic">
          {interimTranscript || finalTranscript || currentSubtitle}
        </p>
      {/if}
    </div>
  </main>

  <!-- Action Icons (bottom-right) -->
  <div class="fixed bottom-5 right-5 flex items-center gap-3">
    <!-- Show/Hide History -->
    <button
      class="w-11 h-11 rounded-full bg-gray-800/80 hover:bg-gray-700 transition-colors flex items-center justify-center border border-gray-700"
      on:click={toggleHistory}
      aria-label="Show history"
      title="Show history"
    >
      <!-- Chat bubble icon -->
      <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 text-gray-200" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <path stroke-linecap="round" stroke-linejoin="round" d="M7 8h10M7 12h7m7-1a8 8 0 10-15.1 3.9L3 20l3.1-.9A8 8 0 1021 11z" />
      </svg>
    </button>

    <!-- Download Summary -->
    <button
      class="w-11 h-11 rounded-full bg-purple-700 hover:bg-purple-600 transition-colors flex items-center justify-center shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
      on:click={handleDownload}
      disabled={conversationHistory.length === 0}
      aria-label="Download summary"
      title="Download summary"
    >
      <!-- Download icon -->
      <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16" />
      </svg>
    </button>
  </div>

  <!-- Slide-in History Panel -->
  <aside
    class="fixed top-0 right-0 h-full w-full max-w-md bg-gray-800/95 backdrop-blur-md border-l border-gray-700 overflow-hidden"
    style="transform: translateX({isHistoryOpen ? '0' : '100%'}); transition: transform 300ms ease-in-out;"
  >
    <div class="h-full flex flex-col">
      <div class="px-5 py-4 border-b border-gray-700 flex items-center justify-between">
        <h2 class="text-lg font-semibold">Conversation History</h2>
        <button
          class="w-9 h-9 rounded-full bg-gray-800 hover:bg-gray-700 flex items-center justify-center border border-gray-700"
          on:click={toggleHistory}
          aria-label="Close history"
          title="Close"
        >
          <!-- X icon -->
          <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-gray-200" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div class="flex-1 overflow-y-auto px-5 py-4 space-y-3">
        {#each conversationHistory as message}
          <div class="item-fade">
            <span class="font-bold capitalize"
              class:text-purple-400={message.role === 'model'}
              class:text-cyan-400={message.role === 'user'}>{message.role === 'model' ? 'Kai' : 'You'}:</span>
            <span class="whitespace-pre-wrap ml-2 text-gray-200">{message.text}</span>
          </div>
        {/each}
      </div>
    </div>
  </aside>
</div>

<style>
  /* Orb breathing animation */
  .breathing {
    animation: breathe 3.2s ease-in-out infinite;
  }
  .breathing-active {
    animation: breatheActive 1.6s ease-in-out infinite;
    box-shadow: 0 0 80px rgba(139, 92, 246, 0.55);
  }
  @keyframes breathe {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.03); }
  }
  @keyframes breatheActive {
    0%, 100% { transform: scale(1.03); }
    50% { transform: scale(1.08); }
  }

  /* Subtitles transitions */
  .subtitle-new {
    animation: fadeIn 350ms ease-out forwards;
  }
  .subtitle-old {
    position: absolute;
    width: 100%;
    left: 0;
    animation: fadeOutDown 450ms ease-in forwards;
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes fadeOutDown {
    from { opacity: 1; transform: translateY(0); }
    to   { opacity: 0; transform: translateY(8px); }
  }

  /* Audio-reactive orb styling driven by CSS vars */
  .orb {
    transform: scale(var(--orb-scale, 1));
    box-shadow:
      0 0 calc(30px + var(--orb-glow, 0px)) rgba(139, 92, 246, 0.45),
      0 0 calc(12px + (var(--orb-glow, 0px) / 2)) rgba(99, 102, 241, 0.30);
    transition: transform 80ms linear, box-shadow 80ms linear;
  }

  /* History item fade */
  .item-fade {
    animation: itemFade 240ms ease-out both;
  }
  @keyframes itemFade {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
  }
</style>