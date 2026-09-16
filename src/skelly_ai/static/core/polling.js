(() => {
  const root = (window.USA = window.USA || {});

  class Poller {
    constructor() {
      this.jobs = new Map();
      this.running = false;
    }

    register(name, fn, intervalMs, { runImmediately = true } = {}) {
      this.jobs.set(name, {
        name,
        fn,
        intervalMs,
        runImmediately,
        timer: null,
        inFlight: false,
        stopped: false,
      });
      if (this.running) this.#startJob(this.jobs.get(name));
      return () => this.unregister(name);
    }

    unregister(name) {
      const job = this.jobs.get(name);
      if (!job) return;
      job.stopped = true;
      if (job.timer) clearTimeout(job.timer);
      this.jobs.delete(name);
    }

    start() {
      if (this.running) return;
      this.running = true;
      for (const job of this.jobs.values()) this.#startJob(job);
    }

    stop() {
      this.running = false;
      for (const job of this.jobs.values()) {
        if (job.timer) clearTimeout(job.timer);
        job.timer = null;
      }
    }

    async runNow(name) {
      const job = this.jobs.get(name);
      if (!job || job.inFlight) return;
      await this.#runJob(job);
    }

    #startJob(job) {
      if (job.stopped || !this.running) return;
      if (job.runImmediately) {
        job.runImmediately = false;
        void this.#runJob(job);
      } else {
        this.#schedule(job);
      }
    }

    #schedule(job) {
      if (job.stopped || !this.running) return;
      if (job.timer) clearTimeout(job.timer);
      job.timer = setTimeout(() => void this.#runJob(job), job.intervalMs);
    }

    async #runJob(job) {
      if (job.inFlight || job.stopped || !this.running) return;
      job.inFlight = true;
      try {
        await job.fn();
      } catch (error) {
        console.error(`USA poller job '${job.name}' failed`, error);
      } finally {
        job.inFlight = false;
        this.#schedule(job);
      }
    }
  }

  root.polling = new Poller();
})();
