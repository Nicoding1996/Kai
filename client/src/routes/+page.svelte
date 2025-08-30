<script>
  let recognition;
  let interimTranscript = '';
  let finalTranscript = '';
  let isListening = false;
  let status = 'Hold to Speak';
  let conversationHistory = [];

  // Prevent duplicate submits and duplicate audio
  let inFlight = false;
  let audioEl = null;
  // Resolver used to await recognition.onend when stopping recognition
  let recognitionEndResolver = null;

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
    };

    // --- ADD THESE NEW EVENT HANDLERS TO FIX THE BUG ---
    recognition.onstart = () => {
      isListening = true;
      status = 'Listening...';
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

      isListening = false;
      if (status === 'Listening...') {
        status = 'Hold to Speak';
      }
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error', event.error);
      isListening = false;
      status = 'Hold to Speak';
    };
    // --- END OF NEW HANDLERS ---
  }

  function handleOrbPress() {
    // If already listening or a request is being processed, ignore
    if (isListening || inFlight) return;
    finalTranscript = '';
    interimTranscript = '';
    recognition.start();
  }

  async function handleOrbRelease() {
    // Prevent duplicate in-flight requests (allows processing even if recognition.onend already fired)
    if (inFlight) return;
    inFlight = true;

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
      console.log("No speech detected.");
      status = 'Hold to Speak';
      inFlight = false;
      return;
    }

    const userMessage = { role: 'user', text: capturedTranscript };
    conversationHistory = [...conversationHistory, userMessage];

    try {
      const response = await fetch('http://localhost:8000/api/conversation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: capturedTranscript, history: conversationHistory }),
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

      // Play audio once: stop any previous playback first
      try {
        if (audioEl) {
          audioEl.pause();
          audioEl.currentTime = 0;
        }
        audioEl = new Audio(`http://localhost:8000${data.audio_url}`);
        await audioEl.play();
      } catch (e) {
        console.error('Error playing audio', e);
      }

    } catch (error) {
      console.error('There was a problem with the fetch operation:', error);
      status = 'Error!';
      conversationHistory = [...conversationHistory, { role: 'system', text: 'Sorry, I encountered an error.' }];
    } finally {
      status = 'Hold to Speak';
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

<div class="flex flex-col items-center justify-center min-h-screen bg-gray-900 text-white font-sans">
  <h1 class="text-3xl md:text-4xl font-bold mb-6 text-center">Kai - Your AI NLP Coach</h1>

  <!-- Chat History Box -->
  <div class="w-full max-w-2xl h-96 flex flex-col-reverse overflow-y-auto p-4 bg-gray-800 rounded-lg mb-6 border border-gray-700">
    <!-- This div is a spacer that pushes content up -->
    <div>
      {#each [...conversationHistory].reverse() as message}
        <div class="mb-4 animate-fade-in">
          <span class="font-bold capitalize" class:text-purple-400={message.role === 'model'} class:text-cyan-400={message.role === 'user'}>{message.role === 'model' ? 'Kai' : 'You'}:</span>
          <span class="whitespace-pre-wrap">{message.text}</span>
        </div>
      {/each}
    </div>
  </div>

  <!-- Live Transcript Area -->
  <div class="w-full max-w-2xl h-12 text-center mb-6">
    <p class="text-lg text-gray-400 italic">{interimTranscript || finalTranscript || '...'}</p>
  </div>

  <!-- Orb Button -->
  <div
    class="relative w-32 h-32 rounded-full flex items-center justify-center text-center cursor-pointer select-none transition-transform duration-200 ease-in-out"
    class:scale-110={isListening}
    on:mousedown={handleOrbPress}
    on:mouseup={handleOrbRelease}
    on:mouseleave={handleOrbRelease}
    role="button"
    tabindex="0"
    aria-label="Hold to speak"
  >
    <div class="absolute inset-0 bg-purple-600 rounded-full animate-pulse-slow" class:animate-none={!isListening} />
    <div class="relative text-white font-semibold">
      {status}
    </div>
  </div>

  <!-- Download Summary Button -->
  <button
    class="mt-6 px-4 py-2 rounded-md bg-purple-700 hover:bg-purple-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
    on:click={handleDownload}
    disabled={conversationHistory.length === 0}
    aria-label="Download session summary"
    title="Download session summary"
  >
    Download Summary
  </button>
</div>

<style>
  .animate-fade-in {
    animation: fadeIn 0.5s ease-in-out;
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .animate-pulse-slow {
      animation: pulse-slow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  }
  @keyframes pulse-slow {
      50% {
          opacity: .7;
      }
  }
</style>