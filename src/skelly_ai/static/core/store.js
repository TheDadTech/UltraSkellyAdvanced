(() => {
  const root = (window.USA = window.USA || {});

  const listeners = new Set();
  let state = Object.freeze({
    connection: {
      online: false,
      lastUpdated: null,
    },
    audio: {
      preferredOutput: null,
      activeOutput: null,
      fallbackActive: false,
      externalBluetooth: {
        connected: false,
        ready: false,
        reconnecting: false,
      },
      skellySpeaker: {
        connected: false,
        ready: false,
        muted: false,
        volume: null,
      },
    },
    hardware: {
      propConnected: false,
      dacReady: false,
    },
    operation: {
      mode: null,
      running: false,
    },
    providers: {
      brain: null,
      voice: null,
    },
    updates: {
      installedVersion: null,
      availableVersion: null,
      updateAvailable: false,
    },
  });

  function clone(value) {
    return value && typeof value === "object"
      ? structuredClone(value)
      : value;
  }

  function merge(base, patch) {
    if (!patch || typeof patch !== "object" || Array.isArray(patch)) {
      return clone(patch);
    }
    const output = { ...(base || {}) };
    for (const [key, value] of Object.entries(patch)) {
      output[key] =
        value && typeof value === "object" && !Array.isArray(value)
          ? merge(output[key], value)
          : value;
    }
    return output;
  }

  function getState() {
    return state;
  }

  function setState(patch, source = "unknown") {
    const previous = state;
    state = Object.freeze(merge(previous, patch));
    for (const listener of listeners) {
      try {
        listener(state, previous, source);
      } catch (error) {
        console.error("USA store listener failed", error);
      }
    }
    return state;
  }

  function subscribe(listener, { immediate = false } = {}) {
    listeners.add(listener);
    if (immediate) listener(state, state, "subscribe");
    return () => listeners.delete(listener);
  }

  function select(selector, listener, { immediate = false } = {}) {
    let lastValue = selector(state);
    if (immediate) listener(lastValue, lastValue, state, "subscribe");
    return subscribe((nextState, previousState, source) => {
      const nextValue = selector(nextState);
      if (Object.is(nextValue, lastValue)) return;
      const previousValue = lastValue;
      lastValue = nextValue;
      listener(nextValue, previousValue, nextState, source, previousState);
    });
  }

  root.store = { getState, setState, subscribe, select };
})();
