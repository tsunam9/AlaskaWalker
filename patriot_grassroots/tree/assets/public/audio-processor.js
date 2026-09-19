class AudioProcessor extends AudioWorkletProcessor {
  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input.length > 0) {
      const inputChannel = input[0];
      const int16Buffer = new Int16Array(inputChannel.length);
      for (let i = 0; i < inputChannel.length; i++) {
        int16Buffer[i] = Math.max(-1, Math.min(1, inputChannel[i])) * 32767;
      }
      this.port.postMessage(int16Buffer.buffer);
    }
    return true;
  }
}

registerProcessor('audio-processor', AudioProcessor);
!function(){try{var e="undefined"!=typeof window?window:"undefined"!=typeof global?global:"undefined"!=typeof globalThis?globalThis:"undefined"!=typeof self?self:{},n=(new e.Error).stack;n&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[n]="2078cdaa-aa46-55cb-a6c5-6565dc876e45")}catch(e){}}();
//# debugId=2078cdaa-aa46-55cb-a6c5-6565dc876e45
