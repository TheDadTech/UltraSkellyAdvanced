(() => {
  const USA = window.USA = window.USA || {};

  const listeners = new Set();

  const state = {
    system: {
      online: false,
      version: null
    },

    prop: {
      connected: false
    },

    audio: {
      preferredOutput: null,
      activeOutput: null,
      fallbackActive: false,

      skellySpeaker: {
        connected: false,
        ready: false,
        muted: false,
        volume: null
      },

      externalBluetooth: {
        connected: false,
        ready: false,
        reconnecting: false,
        deviceName: null
      }
    }
  };

  function notify() {
    for (const listener of listeners) {
      try {
        listener(state);
      } catch (error) {
        console.error("USA store listener failed:", error);
      }
    }
  }

  function merge(target, patch) {
    for (const [key, value] of Object.entries(patch || {})) {
      if (
        value &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        target[key] &&
        typeof target[key] === "object" &&
        !Array.isArray(target[key])
      ) {
        merge(target[key], value);
      } else {
        target[key] = value;
      }
    }
  }

  USA.store = {
    getState() {
      return state;
    },

    setState(patch) {
      merge(state, patch);
      notify();
    },

    subscribe(listener) {
      listeners.add(listener);

      return () => {
        listeners.delete(listener);
      };
    }
  };
})();
