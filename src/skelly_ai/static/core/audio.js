(() => {
  const USA = window.USA = window.USA || {};

  const outputStatus = document.querySelector("#audio-output-status");

  function render(state) {
    if (!outputStatus) return;

    const audio = state?.audio || {};
    const skelly = audio.skellySpeaker || {};
    const external = audio.externalBluetooth || {};
    const preferred = audio.preferredOutput || "skelly";

    if (preferred === "skelly") {
      outputStatus.textContent = skelly.connected
        ? "Skelly connected"
        : "Skelly selected";

      outputStatus.classList.toggle(
        "neutral",
        !skelly.connected
      );

      return;
    }

    if (preferred === "external_bluetooth") {
      if (external.ready) {
        outputStatus.textContent = "External ready";
      } else if (external.connected) {
        outputStatus.textContent =
          "Bluetooth connected · audio starting";
      } else if (audio.fallbackActive && skelly.ready) {
        outputStatus.textContent =
          "External unavailable · using Skelly";
      } else if (external.reconnecting) {
        outputStatus.textContent = "reconnecting…";
      } else {
        outputStatus.textContent = "speaker needed";
      }

      outputStatus.classList.toggle(
        "neutral",
        !external.ready
      );

      return;
    }

    outputStatus.textContent = "Pi / USB audio";
    outputStatus.classList.add("neutral");
  }

  USA.audioUI = {
    render
  };

  USA.store.subscribe(render);
  render(USA.store.getState());
})();