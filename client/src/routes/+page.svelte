<script>
  import { onMount } from 'svelte';

  let recognition;
  let interimTranscript = '';
  let finalTranscript = '';
  let isListening = false;
  let status = 'Tap to Start';
  let conversationHistory = [];

  // Track whether we've already greeted (affects orb label flow)
  let hasGreeted = false;

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

  // Small UI feedback for downloads
  let downloading = false;

  // Highlight download button when conversation concluded
  let conversationEnded = false;

  // Small menu to choose Markdown or PDF download
  let showDownloadMenu = false;

  // One-time hint bubble when conversation ends
  let showDownloadHint = false;

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

  // Ensure coach audio stops immediately (and visualizer) before starting to listen
  function stopCoachAudio() {
    try {
      if (audioEl) {
        audioEl.onplay = null;
        audioEl.onpause = null;
        audioEl.onended = null;
        audioEl.onerror = null;
        audioEl.pause();
        audioEl.currentTime = 0;
      }
    } catch {}
    stopSpeakingViz();
    audioEl = null;
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

    // (Optional) mic hooks could be added here; currently not active in this build.

    const combined = aiLevel;
    orbLevel = combined;

    if (speaking) {
      rafId = requestAnimationFrame(speakingAnimationLoop);
    } else {
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
        status = hasGreeted ? 'Tap to Speak' : 'Tap to Start';
      }
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error', event.error);
      isListening = false;
      status = hasGreeted ? 'Tap to Speak' : 'Tap to Start';
    };
  }

  // Tap-to-toggle handler
  function handleOrbClick() {
    if (inFlight) return;

    if (!isListening) {
      // If coach is currently speaking, stop that audio immediately before we start listening
      if (speaking || audioEl) {
        stopCoachAudio();
      }

      // Close any open menus and reset end-of-convo highlight
      showDownloadMenu = false;
      conversationEnded = false;

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

      // Detect conclusion phrases to highlight download button (case-insensitive)
      const lc = (data.text || '').toLowerCase();
      const endRegex = /(fantastic plan|great work(?: today)?|you['’]ve done great|you have done great|you did great|best of luck|i['’]m here whenever|im here whenever|wonderful!?\s|you've done great work)/i;
      if (endRegex.test(lc)) {
        conversationEnded = true;
        showDownloadHint = true;
        setTimeout(() => (showDownloadHint = false), 4500);
      }
      const last = conversationHistory[conversationHistory.length - 1];
      if (!last || last.role !== 'model' || last.text !== data.text) {
        conversationHistory = [...conversationHistory, aiMessage];
      }
      setSubtitleFromHistory();

      // Play audio once: stop any previous playback first
      try {
        await playAudioFromUrl(`http://localhost:8000${data.audio_url}`, () => {
          // After each AI turn finishes, show Tap to Speak
          hasGreeted = true;
          status = 'Tap to Speak';
        });
      } catch (e) {
        console.error('Error playing audio', e);
      }
    } catch (error) {
      console.error('There was a problem with the fetch operation:', error);
      status = 'Error!';
      conversationHistory = [...conversationHistory, { role: 'system', text: 'Sorry, I encountered an error.' }];
      setSubtitleFromHistory();
    } finally {
      status = 'Tap to Speak';
      hasGreeted = true;
      // Clear transcripts only after we've recorded them into history
      finalTranscript = '';
      interimTranscript = '';
      inFlight = false;
    }
  }

  // Common audio playback + analyser hook
  async function playAudioFromUrl(url, onEndedCb = null) {
    if (audioEl) {
      try {
        audioEl.pause();
        audioEl.currentTime = 0;
      } catch {}
    }
    audioEl = new Audio(url);
    audioEl.crossOrigin = 'anonymous';
    audioEl.muted = false;
    audioEl.volume = 1;

    await ensureAudioCtx();
    if (sourceNode) {
      try { sourceNode.disconnect(); } catch {}
    }
    sourceNode = audioCtx.createMediaElementSource(audioEl);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    dataArray = new Uint8Array(analyser.frequencyBinCount);
    sourceNode.connect(analyser);
    analyser.connect(audioCtx.destination);

    audioEl.onplay = async () => {
      try {
        if (audioCtx.state === 'suspended') await audioCtx.resume();
      } catch {}
      speaking = true;
      if (!rafId) rafId = requestAnimationFrame(speakingAnimationLoop);
      else speakingAnimationLoop();
    };
    const stop = () => {
      stopSpeakingViz();
      if (typeof onEndedCb === 'function') {
        onEndedCb();
      }
    };
    audioEl.onpause = stop;
    audioEl.onended = stop;
    audioEl.onerror = (e) => {
      console.error('Audio element error', e, audioEl.error);
      stopSpeakingViz();
    };

    await audioEl.play();
  }

  // Download session summary as a Markdown file (with feedback)
  async function handleDownload() {
    try {
      if (!conversationHistory || conversationHistory.length === 0) return;
      downloading = true;

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

      const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);

      const a = document.createElement('a');
      a.href = url;
      a.download = 'kai-session-summary.md';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Failed to download summary', e);
    } finally {
      // brief feedback window
      setTimeout(() => (downloading = false), 600);
    }
  }

  // Download session summary as a PDF file (server-rendered)
  async function handleDownloadPdf() {
    try {
      if (!conversationHistory || conversationHistory.length === 0) return;
      downloading = true;

      const response = await fetch('http://localhost:8000/api/summary_pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ history: conversationHistory })
      });

      if (!response.ok) {
        throw new Error(`Network response was not ok: ${response.statusText}`);
      }

      const data = await response.json();
      const pdfUrl = data.pdf_url;
      if (!pdfUrl) throw new Error('No pdf_url returned from server');

      // Fetch the PDF as a blob so we can force a download (cross-origin safe)
      const pdfRes = await fetch(`http://localhost:8000${pdfUrl}`);
      if (!pdfRes.ok) throw new Error('Failed to fetch generated PDF');
      const blob = await pdfRes.blob();
      const url = URL.createObjectURL(blob);

      const a = document.createElement('a');
      a.href = url;
      a.download = 'kai-session-summary.pdf';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Failed to download PDF summary', e);
    } finally {
      setTimeout(() => (downloading = false), 600);
    }
  }

  // Initial greeting: subtitle + TTS playback
  onMount(async () => {
    try {
      const greeting = "Hello, I'm Kai. It's good to hear from you. What's on your mind today?";
      // Show greeting in subtitle and history
      const aiGreeting = { role: 'model', text: greeting };
      conversationHistory = [...conversationHistory, aiGreeting];
      // Push to floating subtitles
      const last = conversationHistory[conversationHistory.length - 1];
      if (last) {
        previousSubtitle = '';
        currentSubtitle = last.text;
      }
      // Request TTS from backend
      const res = await fetch('http://localhost:8000/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: greeting })
      });
      if (res.ok) {
        const { audio_url } = await res.json();
        await playAudioFromUrl(`http://localhost:8000${audio_url}`, () => {
          hasGreeted = true;
          status = 'Tap to Speak';
        });
      } else {
        // If TTS fails, still advance UI
        hasGreeted = true;
        status = 'Tap to Speak';
      }
    } catch (e) {
      console.warn('Initial greeting failed', e);
      hasGreeted = true;
      status = 'Tap to Speak';
    }
  });
</script>

<svelte:head>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@600;700;800&display=swap" rel="stylesheet">
</svelte:head>

<!-- Minimalist, immersive layout -->
<div class="min-h-screen bg-gray-900 text-white font-sans flex flex-col overflow-hidden">
  <!-- Title -->
  <header class="py-4 text-center">
    <h1
      class="title-clean text-3xl md:text-4xl font-semibold tracking-tight"
      style="font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, 'Helvetica Neue', Arial;"
    >
      Kai - Your AI Coach
    </h1>
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
      style={`--orb-scale:${(1 + orbLevel * 0.10).toFixed(3)}; --orb-glow:${Math.round(orbLevel * 100)}px;`}
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
      <!-- High-quality chat bubble icon -->
      <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 text-gray-100 transition-transform duration-150 hover:scale-110" viewBox="0 0 24 24" fill="currentColor">
        <path d="M2 12.75C2 7.365 6.477 3 12 3s10 4.365 10 9.75S17.523 22.5 12 22.5c-1.29 0-2.529-.2-3.679-.574L4 23l1.21-3.239C3.37 18.29 2 15.67 2 12.75zM7 10.5h10a1 1 0 100-2H7a1 1 0 100 2zm0 4h6a1 1 0 100-2H7a1 1 0 100 2z"/>
      </svg>
    </button>

    <!-- Download Summary -->
    <button
      class="w-11 h-11 rounded-full bg-purple-700 hover:bg-purple-600 transition-colors flex items-center justify-center shadow-md disabled:opacity-50 disabled:cursor-not-allowed relative"
      class:animate-pulse={conversationEnded}
      on:click={() => (showDownloadMenu = !showDownloadMenu)}
      disabled={conversationHistory.length === 0}
      aria-label="Download summary"
      title="Download summary"
    >
      {#if downloading}
        <!-- Spinner -->
        <svg class="w-6 h-6 text-white animate-spin" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-30" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
        </svg>
      {:else}
        <!-- High-quality download icon -->
        <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 text-white transition-transform duration-150 hover:scale-110" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 3a1 1 0 011 1v8.586l2.293-2.293a1 1 0 111.414 1.414l-4.004 4.004a1 1 0 01-1.414 0l-4.004-4.004a1 1 0 111.414-1.414L11 12.586V4a1 1 0 011-1z"/>
          <path d="M4 18a2 2 0 012-2h12a2 2 0 012 2v1a2 2 0 01-2 2H6a2 2 0 01-2-2v-1z"/>
        </svg>
      {/if}
    </button>

    <!-- Small download menu -->
    {#if showDownloadMenu}
      <div class="absolute bottom-20 right-5 bg-gray-900/95 border border-gray-700 rounded-md shadow-lg p-2 w-44 backdrop-blur-md">
        <button
          class="w-full text-left px-2 py-1.5 rounded hover:bg-gray-800 text-gray-200 text-sm"
          on:click={() => { showDownloadMenu = false; handleDownload(); }}
        >
          Download as Markdown (.md)
        </button>
        <button
          class="w-full text-left mt-1 px-2 py-1.5 rounded hover:bg-gray-800 text-gray-200 text-sm"
          on:click={() => { showDownloadMenu = false; handleDownloadPdf(); }}
        >
          Download as PDF (.pdf)
        </button>
      </div>
    {/if}

    {#if downloading}
      <div class="absolute bottom-20 right-5 text-sm text-gray-200 bg-gray-800/80 px-3 py-1 rounded-md border border-gray-700 shadow">
        Downloading...
      </div>
    {/if}
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

  /* Subtle professional title treatment */
  .title-clean {
    color: #e9e9f3;
    text-shadow: 0 1px 0 rgba(0,0,0,0.25), 0 2px 12px rgba(88, 28, 135, 0.15);
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