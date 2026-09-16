(() => {
  const USA = window.USA = window.USA || {};

  const jobs = new Map();

  function start(name, callback, intervalMs, { immediate = true } = {}) {
    stop(name);

    let running = false;

    async function run() {
      if (running) return;

      running = true;

      try {
        await callback();
      } catch (error) {
        console.error(`USA polling job "${name}" failed:`, error);
      } finally {
        running = false;
      }
    }

    const timer = setInterval(run, intervalMs);

    jobs.set(name, timer);

    if (immediate) {
      run();
    }
  }

  function stop(name) {
    const timer = jobs.get(name);

    if (timer) {
      clearInterval(timer);
      jobs.delete(name);
    }
  }

  function stopAll() {
    for (const name of [...jobs.keys()]) {
      stop(name);
    }
  }

  USA.polling = {
    start,
    stop,
    stopAll
  };
})();
