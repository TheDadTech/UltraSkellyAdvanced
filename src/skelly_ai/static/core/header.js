(() => {
  const USA = window.USA = window.USA || {};

  const propStatus = document.querySelector("#header-prop-status");
  const speakerStatus = document.querySelector("#header-speaker-status");
  const speakerLabel = document.querySelector("#header-speaker-label");
  const propLight = document.querySelector("#prop-status-light");
  const speakerLight = document.querySelector("#speaker-status-light");

  function setLight(element, state) {
    if (!element) return;

    element.classList.remove("ok", "error", "waiting", "off");
    element.classList.add(state);
  }

  function render(state) {
    const prop = state?.prop || {};
    const audio = state?.audio || {};
    const skelly = audio.skellySpeaker || {};
    const external = audio.externalBluetooth || {};

    if (propStatus) {
      propStatus.textContent = prop.connected
        ? "connected"
        : "disconnected";
    }

    setLight(
      propLight,
      prop.connected ? "ok" : "error"
    );

    const preferred = audio.preferredOutput || "skelly";

    if (preferred === "external_bluetooth") {
      if (speakerLabel) {
        speakerLabel.textContent = audio.fallbackActive
          ? "AUDIO OUTPUT"
          : "EXTERNAL SPEAKER";
      }

      if (speakerStatus) {
        if (external.ready) {
          speakerStatus.textContent = "External ready";
        } else if (external.connected) {
          speakerStatus.textContent =
            "Bluetooth connected · audio starting";
        } else if (audio.fallbackActive && skelly.ready) {
          speakerStatus.textContent =
            "External unavailable · using Skelly";
        } else if (external.reconnecting) {
          speakerStatus.textContent = "reconnecting…";
        } else {
          speakerStatus.textContent = "disconnected";
        }
      }

      setLight(
        speakerLight,
        external.ready || skelly.ready ? "ok" : "off"
      );

      return;
    }

    if (preferred === "system") {
      if (speakerLabel) {
        speakerLabel.textContent = "PI / USB AUDIO";
      }

      if (speakerStatus) {
        speakerStatus.textContent = "connected";
      }

      setLight(speakerLight, "ok");
      return;
    }

    if (speakerLabel) {
      speakerLabel.textContent = "SKELLY SPEAKER";
    }

    if (speakerStatus) {
      speakerStatus.textContent =
        skelly.ready || skelly.connected
          ? "connected"
          : "disconnected";
    }

    setLight(
      speakerLight,
      skelly.ready ? "ok" : "off"
    );
  }

  USA.header = {
    render
  };

  USA.store.subscribe(render);
  render(USA.store.getState());
})();