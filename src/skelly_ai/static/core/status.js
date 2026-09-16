(() => {
  const USA = window.USA = window.USA || {};

  function ingest(body) {
    const settings = body?.operation?.settings || {};
    const route = body?.audio_route || {};
    const skellyAudio = body?.audio || {};
    const externalAudio = body?.external_audio || {};

    const skellyReady = Boolean(
      skellyAudio.connected &&
      (skellyAudio.sink_ready || skellyAudio.sink_id)
    );

    const externalReady = Boolean(
      externalAudio.connected &&
      externalAudio.sink_id
    );

    USA.store.setState({
      system: {
        online: true,
        version: body?.version || null
      },

      prop: {
        connected: Boolean(body?.hardware?.connected)
      },

      audio: {
        preferredOutput: route.preferred || settings.audio_output || "skelly",
        activeOutput: route.active || null,
        fallbackActive: route.fallback_active === true,

        skellySpeaker: {
          connected: Boolean(skellyAudio.connected),
          ready: skellyReady
        },

        externalBluetooth: {
          connected: Boolean(externalAudio.connected),
          ready: externalReady,
          reconnecting:
            Boolean(externalAudio.address) &&
            !externalReady,
          deviceName: externalAudio.device_name || null
        }
      }
    });
  }

  USA.status = {
    ingest
  };
})();