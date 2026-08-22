const connection = document.querySelector("#connection");
const versionPill = document.querySelector("#version-pill");
const updateAvailableBadge = document.querySelector("#update-available-badge");
const topConnectSkelly = document.querySelector("#top-connect-skelly");
const topConnectResult = document.querySelector("#top-connect-result");
const headerPropStatus = document.querySelector("#header-prop-status");
const headerSpeakerStatus = document.querySelector("#header-speaker-status");
const headerDacStatus = document.querySelector("#header-dac-status");
const headerAiStatus = document.querySelector("#header-ai-status");
const headerFppStatus = document.querySelector("#header-fpp-status");
const statusLights = {
  pi: document.querySelector("#pi-status-light"),
  prop: document.querySelector("#prop-status-light"),
  speaker: document.querySelector("#speaker-status-light"),
  dac: document.querySelector("#dac-status-light"),
  ai: document.querySelector("#ai-status-light"),
  fpp: document.querySelector("#fpp-status-light"),
};
const operationSettingsForm = document.querySelector("#operation-settings-form");
const hardwareProfile = document.querySelector("#hardware-profile");
const defaultOperationMode = document.querySelector("#default-operation-mode");
const autoStartOperation = document.querySelector("#auto-start-operation");
const allowFppOverride = document.querySelector("#allow-fpp-override");
const fppOverrideSetting = document.querySelector("#fpp-override-setting");
const operationProfileState = document.querySelector("#profile-state");
const operationSettingsResult = document.querySelector("#operation-settings-result");
const operationReady = document.querySelector("#operation-ready");
const operationSteps = document.querySelector("#operation-steps");
const operationResult = document.querySelector("#operation-result");
const stopOperation = document.querySelector("#stop-operation");
const setupDeviceName = document.querySelector("#setup-device-name");
const setupDeviceDetails = document.querySelector("#setup-device-details");
const setupDeviceStatus = document.querySelector("#setup-device-status");
const startDefaultOperation = document.querySelector("#start-default-operation");
const setupStartDescription = document.querySelector("#setup-start-description");
const setupStartResult = document.querySelector("#setup-start-result");
const firstRunDiscovery = document.querySelector("#first-run-discovery");
const setupDeviceSelect = document.querySelector("#setup-device-select");
const setupConnectDevice = document.querySelector("#setup-connect-device");
const setupRescanDevice = document.querySelector("#setup-rescan-device");
const setupDiscoveryResult = document.querySelector("#setup-discovery-result");
const forgetSkelly = document.querySelector("#forget-skelly");
const forgetSkellyDialog = document.querySelector("#forget-skelly-dialog");
const confirmForgetSkelly = document.querySelector("#confirm-forget-skelly");
const forgetSkellyResult = document.querySelector("#forget-skelly-result");
const speakerVolume = document.querySelector("#speaker-volume");
const speakerVolumeValue = document.querySelector("#speaker-volume-value");
const speakerVolumeResult = document.querySelector("#speaker-volume-result");
const mediaLibrary = document.querySelector("#media-library");
const mediaResult = document.querySelector("#media-result");
const refreshMedia = document.querySelector("#refresh-media");
const addMedia = document.querySelector("#add-media");
const mediaFileInput = document.querySelector("#media-file-input");
const mediaFilter = document.querySelector("#media-filter");
const mediaEditor = document.querySelector("#media-editor");
const mediaEditorForm = document.querySelector("#media-editor-form");
const mediaEditorResult = document.querySelector("#media-editor-result");
const classicLibrarySection = document.querySelector("#classic-library-section");
const localBrainSection = document.querySelector("#local-brain-section");
const manualPropControls = document.querySelector("#manual-prop-controls");
const dacControllerSection = document.querySelector("#dac-controller-section");
const diagnostics = document.querySelector("#diagnostics");
const hardwareConnection = document.querySelector("#hardware-connection");
const hardwareDriver = document.querySelector("#hardware-driver");
const hardwareDevice = document.querySelector("#hardware-device");
const hardwareAddressReadout = document.querySelector("#hardware-address-readout");
const hardwareAddress = document.querySelector("#hardware-address");
const hardwareMotorSafety = document.querySelector("#hardware-motor-safety");
const hardwareDiscovery = document.querySelector("#hardware-discovery");
const hardwareEye = document.querySelector("#hardware-eye");
const hardwareMovement = document.querySelector("#hardware-movement");
const hardwareLiveMode = document.querySelector("#hardware-live-mode");
const hardwareResult = document.querySelector("#hardware-result");
const speakerConnection = document.querySelector("#speaker-connection");
const speakerDevice = document.querySelector("#speaker-device");
const speakerAddress = document.querySelector("#speaker-address");
const speakerConnect = document.querySelector("#speaker-connect");
const speakerDisconnect = document.querySelector("#speaker-disconnect");
const speakerResult = document.querySelector("#speaker-result");
const dacState = document.querySelector("#dac-state");
const dacTarget = document.querySelector("#dac-target");
const dacUniverse = document.querySelector("#dac-universe");
const dacPriority = document.querySelector("#dac-priority");
const dacChannels = document.querySelector("#dac-channels");
const dacPackets = document.querySelector("#dac-packets");
const dacOutput = document.querySelector("#dac-output");
const dacResult = document.querySelector("#dac-result");
const dacArm = document.querySelector("#dac-arm");
const dacRelease = document.querySelector("#dac-release");
const dacCenter = document.querySelector("#dac-center");
const dacJawOpen = document.querySelector("#dac-jaw-open");
const dacJawClose = document.querySelector("#dac-jaw-close");
const dacJawValue = document.querySelector("#dac-jaw-value");
const dacSliders = {
  tilt: document.querySelector("#dac-tilt"),
  yaw: document.querySelector("#dac-yaw"),
  pitch: document.querySelector("#dac-pitch"),
};
const dacValueOutputs = {
  tilt: document.querySelector("#dac-tilt-value"),
  yaw: document.querySelector("#dac-yaw-value"),
  pitch: document.querySelector("#dac-pitch-value"),
};
const elevenlabsKeyStatus = document.querySelector("#elevenlabs-key-status");
const elevenlabsResult = document.querySelector("#elevenlabs-result");
const updateVersion = document.querySelector("#update-version");
const updateResult = document.querySelector("#update-result");
const checkForUpdates = document.querySelector("#check-for-updates");
const downloadUpdate = document.querySelector("#download-update");
const installUpdate = document.querySelector("#install-update");
let updateMonitorActive = false;
const cameraAvailability = document.querySelector("#camera-availability");
const cameraDevice = document.querySelector("#camera-device");
const cameraPresence = document.querySelector("#camera-presence");
const cameraFaces = document.querySelector("#camera-faces");
const cameraPeople = document.querySelector("#camera-people");
const cameraMotion = document.querySelector("#camera-motion");
const cameraFrame = document.querySelector("#camera-frame");
const cameraPlaceholder = document.querySelector("#camera-placeholder");
const cameraResult = document.querySelector("#camera-result");
const microphoneAvailability = document.querySelector("#microphone-availability");
const microphoneDevice = document.querySelector("#microphone-device");
const microphoneVoice = document.querySelector("#microphone-voice");
const microphoneLevel = document.querySelector("#microphone-level");
const microphonePeak = document.querySelector("#microphone-peak");
const microphoneMeter = document.querySelector("#microphone-meter");
const microphonePlayback = document.querySelector("#microphone-playback");
const microphoneResult = document.querySelector("#microphone-result");
const speechModelStatus = document.querySelector("#speech-model-status");
const microphoneTranscript = document.querySelector("#microphone-transcript");
const transcriptionTime = document.querySelector("#transcription-time");
const transcribeMicrophone = document.querySelector("#transcribe-microphone");
const perceptionState = document.querySelector("#perception-state");
const perceptionPhase = document.querySelector("#perception-phase");
const interactionCue = document.querySelector("#interaction-cue");
const interactionCueTitle = document.querySelector("#interaction-cue-title");
const interactionCueHelp = document.querySelector("#interaction-cue-help");
const perceptionArmed = document.querySelector("#perception-armed");
const perceptionConfirmation = document.querySelector("#perception-confirmation");
const perceptionEventCount = document.querySelector("#perception-event-count");
const perceptionEvents = document.querySelector("#perception-events");
const perceptionResult = document.querySelector("#perception-result");
const startPerception = document.querySelector("#start-perception");
const stopPerception = document.querySelector("#stop-perception");
const brainAvailability = document.querySelector("#brain-availability");
const brainTestForm = document.querySelector("#brain-test-form");
const brainTestInput = document.querySelector("#brain-test-input");
const brainTestButton = document.querySelector("#brain-test-button");
const brainResult = document.querySelector("#brain-result");
const brainVoiceButton = document.querySelector("#brain-voice-button");
const brainResetButton = document.querySelector("#brain-reset-button");
const brainHeardText = document.querySelector("#brain-heard-text");
const operatorCameraFrame = document.querySelector("#operator-camera-frame");
const operatorCameraPlaceholder = document.querySelector("#operator-camera-placeholder");
const operatorCameraResult = document.querySelector("#operator-camera-result");
const gestureCapability = document.querySelector("#gesture-capability");
const gestureResult = document.querySelector("#gesture-result");
const operatorGestureButtons = [...document.querySelectorAll("[data-operator-gesture]")];
const stopOperatorGesture = document.querySelector("#stop-operator-gesture");
const manualCameraEnabled = document.querySelector("#manual-camera-enabled");
const manualMicrophoneEnabled = document.querySelector("#manual-microphone-enabled");
const manualVisitorIndicator = document.querySelector("#manual-visitor-indicator");
const providerState = document.querySelector("#provider-state");
const providerResult = document.querySelector("#provider-result");
const providerWarning = document.querySelector("#provider-warning");
const providerForm = document.querySelector("#provider-settings-form");
const brainProvider = document.querySelector("#brain-provider");
const voiceProvider = document.querySelector("#voice-provider");
const brainProviderHelp = document.querySelector("#brain-provider-help");
const voiceProviderHelp = document.querySelector("#voice-provider-help");
const localVoice = document.querySelector("#local-voice");
const localSpeed = document.querySelector("#local-speed");
const localPitch = document.querySelector("#local-pitch");
const localGap = document.querySelector("#local-gap");
const speakerPreroll = document.querySelector("#speaker-preroll");
const groqVoice = document.querySelector("#groq-voice");
const groqVoiceStyle = document.querySelector("#groq-voice-style");
const elevenlabsVoiceId = document.querySelector("#elevenlabs-voice-id");
const elevenlabsModel = document.querySelector("#elevenlabs-model");
const elevenlabsSpeed = document.querySelector("#elevenlabs-speed");
const elevenlabsVolume = document.querySelector("#elevenlabs-volume");
const jawActivity = document.querySelector("#jaw-activity");
const groqKeyStatus = document.querySelector("#groq-key-status");
const groqResult = document.querySelector("#groq-result");
const previewVoice = document.querySelector("#preview-voice");
const providerCustomPreset = document.querySelector("#provider-custom-preset");
const copyVoicePrompt = document.querySelector("#copy-voice-prompt");
const voiceDesignPrompt = document.querySelector("#voice-design-prompt");
const copyVoicePromptResult = document.querySelector("#copy-voice-prompt-result");
const onboardingDialog = document.querySelector("#onboarding-dialog");
const onboardingNetworkStep = document.querySelector("#onboarding-network-step");
const onboardingDisclaimerStep = document.querySelector("#onboarding-disclaimer-step");
const onboardingWifiSelect = document.querySelector("#onboarding-wifi-select");
const onboardingWifiManual = document.querySelector("#onboarding-wifi-manual");
const onboardingWifiPassword = document.querySelector("#onboarding-wifi-password");
const onboardingNetworkResult = document.querySelector("#onboarding-network-result");
const onboardingAcceptCheck = document.querySelector("#onboarding-accept-check");
const onboardingAccept = document.querySelector("#onboarding-accept");
const onboardingDisclaimerResult = document.querySelector("#onboarding-disclaimer-result");
const setupWifiSelect = document.querySelector("#setup-wifi-select");
const setupWifiManual = document.querySelector("#setup-wifi-manual");
const setupWifiPassword = document.querySelector("#setup-wifi-password");
const setupWifiResult = document.querySelector("#setup-wifi-result");
const wifiModeStatus = document.querySelector("#wifi-mode-status");
const sshStatus = document.querySelector("#ssh-status");
const sshPassword = document.querySelector("#ssh-password");
const sshPersistent = document.querySelector("#ssh-persistent");
const sshResult = document.querySelector("#ssh-result");
const controllerPowerResult = document.querySelector("#controller-power-result");
let cameraObjectUrl = null;
let operatorCameraObjectUrl = null;
let brainBusy = false;
let currentControllerMode = "unknown";
let currentOperationSettings = null;
let currentOperationMode = "standby";
let currentMediaStatus = null;
let manualCameraPolling = false;
let gestureRequestId = 0;
let operatorListenGestureAvailable = false;
let firstRunDiscoveryStarted = false;
let selectDashboardTab = () => {};

function initializeDashboardTabs() {
  const panels = Object.fromEntries(
    [...document.querySelectorAll("[data-dashboard-panel]")].map((panel) => [
      panel.dataset.dashboardPanel,
      panel,
    ]),
  );
  const layout = {
    operate: [
      document.querySelector("#mode-launcher-section"),
      document.querySelector("#classic-library-section"),
      document.querySelector(".perception-monitor"),
      document.querySelector("#local-brain-section"),
      document.querySelector("#manual-prop-controls"),
    ],
    setup: [
      document.querySelector("#operation-preferences-section"),
      document.querySelector("#replace-skelly-section"),
      document.querySelector("#prop-controller-section"),
      document.querySelector("#wifi-settings-section"),
    ],
    voice: [
      document.querySelector("#ai-services-section"),
      document.querySelector("#elevenlabs-section"),
    ],
    diagnostics: [
      document.querySelector("#sensor-lab-section"),
      document.querySelector("#advanced-bluetooth-section"),
      document.querySelector("#dac-controller-section"),
      document.querySelector("#software-update-section"),
      document.querySelector("#ssh-access-section"),
      document.querySelector("#controller-power-section"),
      document.querySelector("#diagnostics-section"),
    ],
  };
  Object.entries(layout).forEach(([name, sections]) => {
    sections.filter(Boolean).forEach((section) => panels[name].append(section));
  });

  const tabs = [...document.querySelectorAll("[data-dashboard-tab]")];
  selectDashboardTab = function selectTab(name, { focus = false } = {}) {
    tabs.forEach((tab) => {
      const selected = tab.dataset.dashboardTab === name;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      if (selected && focus) tab.focus();
    });
    Object.entries(panels).forEach(([panelName, panel]) => {
      panel.hidden = panelName !== name;
    });
    try {
      localStorage.setItem("skelly-dashboard-tab", name);
    } catch {
      // Private browsing and hardened kiosk policies can disable local storage.
    }
  };

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectDashboardTab(tab.dataset.dashboardTab));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const offset = event.key === "ArrowRight" ? 1 : -1;
      const next = tabs[(index + offset + tabs.length) % tabs.length];
      selectDashboardTab(next.dataset.dashboardTab, { focus: true });
    });
  });
  let saved = null;
  try {
    saved = localStorage.getItem("skelly-dashboard-tab");
  } catch {
    // The Operate tab remains the safe default when persistence is unavailable.
  }
  selectDashboardTab(panels[saved] ? saved : "operate");
}

initializeDashboardTabs();

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

function setStatusLight(light, state) {
  light.classList.remove("ok", "error", "off", "waiting");
  light.classList.add(state);
}

function updateModeVisibility(activeMode, profile) {
  const readyMode = ["classic", "ai", "manual"].includes(activeMode) ? activeMode : null;
  classicLibrarySection.hidden = readyMode !== "classic";
  document.querySelector(".perception-monitor").hidden = readyMode !== "ai";
  localBrainSection.hidden = readyMode !== "manual";
  manualPropControls.hidden = readyMode !== "manual";
  dacControllerSection.hidden = profile !== "dac";
  document.querySelectorAll("[data-start-operation]").forEach((button) => {
    const selected = button.dataset.startOperation === activeMode;
    button.closest(".mode-card")?.classList.toggle("active", selected);
    button.disabled = activeMode === "starting" || selected;
  });
  stopOperation.disabled = !readyMode && activeMode !== "needs_attention";
}

function operationModeName(mode) {
  return {
    classic: "Classic Mode",
    ai: "AI Mode",
    manual: "Operator Mode",
    idle: "Remain idle",
    standby: "standby",
    starting: "starting",
    needs_attention: "needs attention",
  }[mode] || String(mode).replaceAll("_", " ");
}

function renderFppOverrideAvailability(profile) {
  const available = profile === "dac";
  fppOverrideSetting.hidden = !available;
  allowFppOverride.disabled = !available;
  if (!available) allowFppOverride.checked = false;
}

function renderOperation(operation) {
  const settings = operation.settings;
  currentOperationSettings = settings;
  currentOperationMode = operation.active_mode;
  if (document.activeElement !== hardwareProfile) hardwareProfile.value = settings.hardware_profile;
  if (document.activeElement !== defaultOperationMode) defaultOperationMode.value = settings.default_mode;
  autoStartOperation.checked = settings.auto_start === true && settings.default_mode !== "idle";
  autoStartOperation.disabled = settings.default_mode === "idle";
  allowFppOverride.checked = settings.allow_fpp_override;
  renderFppOverrideAvailability(settings.hardware_profile);
  manualCameraEnabled.checked = settings.manual_camera_enabled !== false;
  manualMicrophoneEnabled.checked = settings.manual_microphone_enabled !== false;
  brainVoiceButton.disabled = !manualMicrophoneEnabled.checked;
  operationProfileState.textContent = settings.hardware_profile === "dac"
    ? "Advanced: DAC + ESP32"
    : "Stock: no DAC required";
  operationProfileState.classList.toggle("neutral", settings.hardware_profile !== "dac");
  document.querySelectorAll("[data-mode-card]").forEach((card) => {
    card.classList.toggle("featured", card.dataset.modeCard === settings.default_mode);
  });
  const defaultName = operationModeName(settings.default_mode);
  startDefaultOperation.textContent = settings.default_mode === "idle"
    ? "Remain idle"
    : `Start ${defaultName}`;
  setupStartDescription.textContent = settings.default_mode === "idle"
    ? "Leave all interaction and motor outputs safely released."
    : `Connect control, prepare the speaker and motors required by ${defaultName}, then begin.`;
  startDefaultOperation.disabled = settings.device_configured === false || operation.active_mode === "starting";
  operationReady.textContent = operation.ready
    ? `${operationModeName(operation.active_mode)} ready`
    : operationModeName(operation.active_mode);
  operationReady.classList.toggle("neutral", !operation.ready);
  operationSteps.replaceChildren();
  const steps = operation.steps?.length ? operation.steps : ["Select a mode to begin."];
  steps.forEach((step) => {
    const item = document.createElement("li");
    item.textContent = step;
    operationSteps.append(item);
  });
  if (operation.last_error) operationResult.textContent = operation.last_error;
  updateModeVisibility(operation.active_mode, settings.hardware_profile);
}

function renderStatus(body) {
  currentControllerMode = body.state.mode;
  elevenlabsKeyStatus.textContent = body.device.elevenlabs_key_configured ? "key saved" : "not saved";
  groqKeyStatus.textContent = body.device.groq_key_configured ? "key saved" : "not saved";
  connection.textContent = "online";
  const skellyVersion = body.hardware.connected
    ? (body.hardware.firmware_version || "XX")
    : "XX";
  versionPill.textContent = `Skelly ${skellyVersion} · USA ${body.version}`;
  setStatusLight(statusLights.pi, "ok");
  headerPropStatus.textContent = body.hardware.connected ? "connected" : "disconnected";
  setStatusLight(statusLights.prop, body.hardware.connected ? "ok" : "error");
  const speakerReady = Boolean(body.audio.connected && body.audio.sink_ready);
  headerSpeakerStatus.textContent = speakerReady ? "connected" : "disconnected";
  setStatusLight(statusLights.speaker, speakerReady ? "ok" : "off");
  const profile = body.operation?.settings?.hardware_profile ?? "stock";
  headerDacStatus.textContent = profile === "dac"
    ? body.dac.transmitting ? "active" : body.dac.armed ? "armed" : "disarmed"
    : "stock control";
  setStatusLight(
    statusLights.dac,
    profile === "dac" ? (body.dac.armed ? "ok" : "off") : "ok",
  );
  const fppAllowed = Boolean(body.operation?.settings?.allow_fpp_override);
  headerFppStatus.textContent = fppAllowed ? "allowed" : "disabled";
  setStatusLight(statusLights.fpp, fppAllowed ? "ok" : "off");
  topConnectSkelly.disabled = false;
  topConnectSkelly.dataset.connected = String(body.hardware.connected);
  topConnectSkelly.classList.toggle("disconnect", body.hardware.connected);
  topConnectSkelly.textContent = body.hardware.connected ? "Disconnect Skelly" : "Connect to Skelly";
  if (body.operation) {
    renderOperation(body.operation);
    const configured = body.operation.settings.device_configured !== false;
    const profileName = body.operation.settings.hardware_profile === "dac"
      ? "Advanced hardware · DAC + ESP32"
      : "Standard hardware · no DAC";
    setupDeviceName.textContent = configured
      ? body.hardware.device_name || body.device.name || "Saved Skelly"
      : "No Skelly configured";
    setupDeviceDetails.textContent = configured
      ? `${profileName} · Speaker ${speakerReady ? "connected" : body.audio.paired ? "paired" : "not connected"}`
      : "Use Connect to Skelly in the header to choose a prop.";
    setupDeviceStatus.textContent = !configured
      ? "setup needed"
      : body.hardware.connected ? "ready to operate" : "saved · offline";
    setupDeviceStatus.classList.toggle("neutral", !configured || !body.hardware.connected);
    firstRunDiscovery.hidden = configured;
    if (!configured && !firstRunDiscoveryStarted) {
      firstRunDiscoveryStarted = true;
      selectDashboardTab("setup");
      window.setTimeout(() => discoverSetupDevices(), 150);
    }
  } else {
    operationResult.textContent = `The running Pi service is ${body.version}. Restart the updated service before using these controls.`;
    operationReady.textContent = "update required";
    document.querySelectorAll("[data-start-operation]").forEach((button) => { button.disabled = true; });
  }
  hardwareConnection.textContent = body.hardware.connected ? "prop connected" : "prop disconnected";
  hardwareConnection.classList.toggle("neutral", !body.hardware.connected);
  hardwareDriver.textContent = body.hardware.driver;
  hardwareDevice.textContent = body.hardware.device_name || "not selected";
  hardwareAddressReadout.textContent = body.hardware.address || "not selected";
  if (!hardwareAddress.value && body.hardware.address) hardwareAddress.value = body.hardware.address;
  hardwareEye.textContent = `${body.hardware.eye_icon} (${body.hardware.eye_index})`;
  hardwareMovement.textContent = body.hardware.movement.replaceAll("_", " ");
  hardwareMotorSafety.textContent = body.hardware.movement_armed ? "enabled" : "disabled";
  hardwareLiveMode.textContent = body.hardware.live_mode ? "on" : "off";
  document.querySelectorAll("[data-live-mode-command]").forEach((button) => {
    button.disabled = !body.hardware.connected;
  });
  document.querySelectorAll("[data-movement-command]").forEach((button) => {
    button.disabled = !body.hardware.connected || !body.hardware.movement_armed;
  });
  renderAudioStatus(body.audio, body.state.mode);
  const dac = body.dac;
  dacState.textContent = dac.transmitting ? "transmitting" : dac.armed ? "armed" : "disarmed";
  dacState.classList.toggle("neutral", !dac.transmitting);
  dacTarget.textContent = `${dac.target}:${dac.port}`;
  dacUniverse.textContent = String(dac.universe);
  dacPriority.textContent = `${dac.priority} at ${dac.fps} FPS`;
  dacChannels.textContent = `jaw ${dac.channels.jaw}, tilt ${dac.channels.tilt}, no ${dac.channels.yaw}, yes ${dac.channels.pitch}`;
  dacPackets.textContent = String(dac.packet_count);
  dacOutput.textContent = dac.transmitting ? "active" : "stopped";
  const dacControlsEnabled = dac.armed && body.state.mode !== "show_locked";
  const advancedGestures = profile === "dac";
  operatorListenGestureAvailable = advancedGestures && dac.armed && currentOperationMode === "manual";
  gestureCapability.textContent = advancedGestures
    ? dac.armed ? "advanced puppeteering ready" : "DAC profile · start Operator Mode"
    : "standard controls · Laugh available";
  gestureCapability.classList.toggle("neutral", !advancedGestures || !dac.armed);
  document.querySelectorAll(".gesture-dac").forEach((button) => {
    button.disabled = !advancedGestures || !dac.armed || currentOperationMode !== "manual";
    button.classList.toggle("requires-dac", !advancedGestures);
    button.title = advancedGestures
      ? ""
      : "Enable the Advanced DAC profile for precise head positioning";
  });
  operatorGestureButtons.filter((button) => !button.classList.contains("gesture-dac")).forEach((button) => {
    button.disabled = currentOperationMode !== "manual";
  });
  stopOperatorGesture.disabled = currentOperationMode !== "manual";
  Object.entries(dacSliders).forEach(([name, slider]) => {
    slider.disabled = !dacControlsEnabled;
    if (document.activeElement !== slider) slider.value = String(dac.values[name]);
    dacValueOutputs[name].textContent = slider.value;
  });
  dacJawValue.textContent = dac.values.jaw === 0 ? "closed (0)" : "open (255)";
  dacJawOpen.disabled = !dacControlsEnabled;
  dacJawClose.disabled = !dacControlsEnabled;
  dacCenter.disabled = !dacControlsEnabled;
  dacArm.disabled = dac.armed || body.state.mode === "show_locked";
}

function renderAudioStatus(audio, currentMode = currentControllerMode) {
  const available = Boolean(audio?.available);
  const connected = Boolean(audio?.connected);
  const sinkReady = Boolean(audio?.sink_ready);
  speakerConnection.textContent = connected && sinkReady
    ? "connected + routed"
    : connected
      ? "connected (route audio)"
    : available
      ? "disconnected"
      : "unavailable";
  speakerConnection.classList.toggle("neutral", !connected || !sinkReady);
  speakerDevice.textContent = audio?.device_name || "not selected";
  speakerAddress.textContent = audio?.address || "not selected";
  const showLocked = currentMode === "show_locked";
  speakerConnect.disabled = !available || (connected && sinkReady) || showLocked;
  speakerDisconnect.disabled = !available || !connected || showLocked;
}

async function refreshAudioStatus() {
  const audio = await request("/api/audio/status");
  renderAudioStatus(audio);
  return audio;
}

async function refreshStatus() {
  try {
    renderStatus(await request("/api/status"));
  } catch (error) {
    connection.textContent = `Unable to reach the local service: ${error.message}`;
    setStatusLight(statusLights.pi, "error");
  }
}

function renderAvailability(element, available) {
  element.textContent = available ? "available" : "unavailable";
  element.classList.toggle("neutral", !available);
}

function renderSensorStatus(body) {
  const camera = body.camera;
  const microphone = body.microphone;
  renderAvailability(cameraAvailability, camera.available);
  renderAvailability(microphoneAvailability, microphone.available);
  cameraDevice.textContent = camera.device;
  microphoneDevice.textContent = microphone.resolved_device || microphone.device;
  cameraPresence.textContent = camera.analyzed
    ? (camera.presence_detected ? "detected" : "clear")
    : "not tested";
  const visitorDetected = Boolean(camera.analyzed && camera.presence_detected);
  manualVisitorIndicator.classList.toggle("detected", visitorDetected);
  manualVisitorIndicator.classList.toggle("clear", !visitorDetected);
  const visitorLight = manualVisitorIndicator.querySelector(".status-light");
  setStatusLight(visitorLight, visitorDetected ? "ok" : manualCameraEnabled.checked ? "off" : "error");
  manualVisitorIndicator.querySelector("strong").textContent = !manualCameraEnabled.checked
    ? "Camera disabled"
    : visitorDetected
      ? "Visitor detected"
      : "No visitor detected";
  cameraFaces.textContent = camera.face_count;
  cameraPeople.textContent = camera.person_count;
  cameraMotion.textContent = `${camera.motion_percent}%`;
  microphoneVoice.textContent = microphone.sampled
    ? (microphone.voice_active ? "detected" : "quiet")
    : "not tested";
  microphoneLevel.textContent = microphone.level_dbfs === null
    ? "—"
    : `${microphone.level_dbfs} dBFS`;
  microphonePeak.textContent = `${microphone.peak_percent}%`;
  microphoneMeter.style.width = `${Math.max(0, Math.min(100, microphone.peak_percent))}%`;
  speechModelStatus.textContent = microphone.offline_transcription_available
    ? `Offline model ready: ${microphone.speech_model}`
    : `Offline model not installed: ${microphone.speech_model}`;
  transcribeMicrophone.disabled = !microphone.offline_transcription_available;
  if (microphone.transcript !== null && microphone.transcript !== undefined) {
    microphoneTranscript.textContent = microphone.transcript || "No speech recognized";
    transcriptionTime.textContent = microphone.transcription_seconds === null
      ? ""
      : `Processed locally in ${microphone.transcription_seconds} seconds`;
  }
}

async function refreshSensorStatus() {
  renderSensorStatus(await request("/api/sensors/status"));
}

async function pollManualCamera() {
  if (manualCameraPolling || currentOperationMode !== "manual" || !manualCameraEnabled.checked) return;
  manualCameraPolling = true;
  try {
    await fetch(`/api/sensors/camera/frame.jpg?t=${Date.now()}`, { cache: "no-store" });
    await refreshSensorStatus();
  } catch {
    // The persistent status indicator reports camera availability without interrupting operation.
  } finally {
    manualCameraPolling = false;
  }
}

function renderPerceptionStatus(body) {
  perceptionState.textContent = body.enabled ? "monitoring" : "stopped";
  perceptionState.classList.toggle("neutral", !body.enabled);
  headerAiStatus.textContent = body.enabled ? body.phase.replaceAll("_", " ") : "stopped";
  setStatusLight(
    statusLights.ai,
    body.phase === "sensor_error" ? "error" : body.enabled ? "ok" : "off",
  );
  perceptionPhase.textContent = body.phase.replaceAll("_", " ");
  const cueStates = {
    stopped: ["idle", "AI MODE STOPPED", "Start AI Mode when you are ready for visitors."],
    starting: ["detected", "STARTING AI MODE", "Preparing the camera and microphone."],
    scanning: ["idle", "WAITING FOR A VISITOR", "Skelly is watching for someone to approach."],
    confirming_presence: ["detected", "VISITOR DETECTED", "Hold still for just a moment."],
    visitor_confirmed: ["detected", "GET READY TO SPEAK", "Skelly has seen you."],
    waiting_to_listen: ["detected", "GET READY TO SPEAK", "The microphone will open momentarily."],
    listening: ["listening", "SPEAK NOW — I'M LISTENING", "Skelly's green eyes also mean the microphone is open."],
    thinking: ["thinking", "THINKING…", "Skelly's spiral eyes mean your answer is being prepared."],
    response_ready: ["detected", "READY FOR THE NEXT TURN", "Skelly will listen again while you remain nearby."],
    transcript_captured: ["detected", "I HEARD YOU", "Your words were captured."],
    no_speech: ["error", "I DIDN'T HEAR THAT", "Wait for green eyes, then speak clearly."],
    confirming_departure: ["idle", "WAITING FOR VISITOR", "The current visitor may have stepped away."],
    rearmed: ["idle", "READY FOR A NEW VISITOR", "Skelly is watching again."],
    paused_for_show: ["thinking", "SHOW MODE ACTIVE", "Visitor listening is paused until the show ends."],
    sensor_error: ["error", "SENSOR NEEDS ATTENTION", body.last_error || "Check the camera and microphone."],
  };
  const [cueClass, cueTitle, cueHelp] = cueStates[body.phase] || ["idle", body.phase.replaceAll("_", " ").toUpperCase(), "Skelly AI is running."];
  interactionCue.className = `interaction-cue ${cueClass}`;
  interactionCueTitle.textContent = cueTitle;
  interactionCueHelp.textContent = cueHelp;
  perceptionArmed.textContent = body.session_active ? "conversation active" : "waiting";
  perceptionConfirmation.textContent = body.session_active
    ? `${body.clear_streak} / ${body.clear_confirmations_required} clear`
    : `${body.presence_streak} / ${body.presence_confirmations_required} present`;
  perceptionEventCount.textContent = `${body.turn_count} / ${body.event_count}`;
  startPerception.disabled = body.enabled;
  stopPerception.disabled = !body.enabled;

  perceptionEvents.replaceChildren();
  if (!body.events.length) {
    const empty = document.createElement("li");
    empty.className = "muted";
    empty.textContent = "No visitor speech captured yet.";
    perceptionEvents.append(empty);
  } else {
    body.events.forEach((event) => {
      const item = document.createElement("li");
      const transcript = document.createElement("strong");
      transcript.textContent = `“${event.transcript}”`;
      const detail = document.createElement("div");
      const occurred = new Date(event.occurred_at).toLocaleTimeString();
      detail.textContent = `${occurred} · faces ${event.face_count} · people ${event.person_count} · ${event.voice_level_dbfs} dBFS`;
      detail.className = "muted";
      item.append(transcript, detail);
      if (event.ai_response) {
        const reply = document.createElement("div");
        reply.className = "ai-event-response";
        reply.textContent = `Skelly: ${event.ai_response}`;
        const actions = document.createElement("small");
        actions.className = "muted";
        const voice = event.speech_spoken ? "spoken through Skelly" : "text only";
        const timings = [
          `listen ${event.listening_seconds ?? "?"}s`,
          `STT finish ${event.transcription_seconds ?? "?"}s${event.transcription_mode === "streaming" ? " (live)" : ""}`,
          `AI ${event.ai_generation_seconds ?? "?"}s (${event.brain_provider ?? "unknown"})`,
        ];
        if (event.voice_generation_seconds != null) {
          const voiceLabel = event.voice_provider === "elevenlabs" ? "first audio" : "voice";
          timings.push(`${voiceLabel} ${event.voice_generation_seconds}s (${event.voice_provider ?? "cloud"})`);
        }
        if (event.playback_seconds != null) {
          timings.push(`${event.voice_provider === "elevenlabs" ? "stream + play" : "playback"} ${event.playback_seconds}s`);
        } else if (event.speech_seconds != null) {
          timings.push(`speech ${event.speech_seconds}s`);
        }
        actions.textContent = `${event.eye_icon} eyes | ${event.movement.replaceAll("_", " ")} | ${voice} | ${timings.join(" | ")}`;
        item.append(reply, actions);
        if (event.brain_fallback_reason || event.voice_fallback_reason) {
          const fallback = document.createElement("div");
          fallback.className = "result";
          fallback.textContent = `Automatic local fallback: ${event.brain_fallback_reason || event.voice_fallback_reason}`;
          item.append(fallback);
        }
        if (event.speech_error) {
          const speechError = document.createElement("div");
          speechError.className = "result";
          speechError.textContent = `Speech playback failed: ${event.speech_error}`;
          item.append(speechError);
        }
      } else if (event.ai_error) {
        const error = document.createElement("div");
        error.className = "result";
        error.textContent = `Local response unavailable: ${event.ai_error}`;
        item.append(error);
      }
      perceptionEvents.append(item);
    });
  }
  if (body.last_error) perceptionResult.textContent = body.last_error;
}

async function refreshPerceptionStatus() {
  renderPerceptionStatus(await request("/api/perception/status"));
}

function renderBrainStatus(body) {
  const voiceReady = Boolean(body.local_speech?.available || body.voice_provider !== "local");
  brainAvailability.textContent = voiceReady ? "operator voice ready" : "voice unavailable";
  brainAvailability.classList.toggle("neutral", !voiceReady);
  brainTestButton.disabled = !voiceReady || brainBusy;
  brainVoiceButton.disabled = brainBusy || !manualMicrophoneEnabled.checked;
  brainResetButton.disabled = brainBusy;
  if (!voiceReady) brainResult.textContent = "Choose a working voice in Voice Tuning.";
}

function providerPayload() {
  return {
    brain_provider: brainProvider.value,
    voice_provider: voiceProvider.value,
    local_voice: localVoice.value,
    local_speed: Number(localSpeed.value),
    local_pitch: Number(localPitch.value),
    local_word_gap: Number(localGap.value),
    groq_voice: groqVoice.value,
    groq_voice_style: groqVoiceStyle.value,
    elevenlabs_voice_id: elevenlabsVoiceId.value.trim(),
    elevenlabs_model: elevenlabsModel.value,
    elevenlabs_speed: Number(elevenlabsSpeed.value),
    elevenlabs_volume_percent: Number(elevenlabsVolume.value),
    speaker_preroll_ms: Number(speakerPreroll.value),
    jaw_activity_percent: Number(jawActivity.value),
  };
}

function updateProviderHelp() {
  brainProviderHelp.textContent = brainProvider.value === "groq"
    ? "Fast cloud responses using the owner's Groq quota."
    : "Private and offline, but slower on a Raspberry Pi 4.";
  voiceProviderHelp.textContent = voiceProvider.value === "groq"
    ? "Natural Orpheus speech using the owner’s Groq account limits."
    : voiceProvider.value === "elevenlabs"
      ? `${elevenlabsModel.value === "eleven_v3" ? "Preview-quality v3" : "Lower-latency"} speech; character credits may be used.`
      : "No cloud usage. Character voice remains intentionally synthetic.";
  providerState.textContent = `${brainProvider.value} brain + ${voiceProvider.value} voice`;
  providerState.classList.toggle(
    "neutral",
    brainProvider.value === "local" && voiceProvider.value === "local",
  );
  renderProviderPresetState();
}

function selectedProviderPreset() {
  if (brainProvider.value === "local" && voiceProvider.value === "local") return "offline";
  if (brainProvider.value === "groq" && voiceProvider.value === "groq") return "cloud";
  if (brainProvider.value === "groq" && voiceProvider.value === "elevenlabs") return "best";
  return "custom";
}

function renderProviderPresetState() {
  const selected = selectedProviderPreset();
  document.querySelectorAll("[data-provider-preset]").forEach((button) => {
    const active = button.dataset.providerPreset === selected;
    button.classList.toggle("selected", active);
    button.classList.toggle("secondary", !active);
    button.setAttribute("aria-pressed", String(active));
  });
  providerCustomPreset.hidden = selected !== "custom";
  providerCustomPreset.classList.toggle("selected", selected === "custom");
  providerCustomPreset.classList.toggle("secondary", selected !== "custom");
  providerCustomPreset.setAttribute("aria-pressed", String(selected === "custom"));
}

function renderProviderStatus(body) {
  localVoice.replaceChildren(...body.local_voices.map((name) => new Option(name, name)));
  groqVoice.replaceChildren(...body.groq_voices.map((name) => new Option(name, name)));
  const settings = body.settings;
  brainProvider.value = settings.brain_provider;
  voiceProvider.value = settings.voice_provider;
  localVoice.value = settings.local_voice;
  localSpeed.value = settings.local_speed;
  localPitch.value = settings.local_pitch;
  localGap.value = settings.local_word_gap;
  groqVoice.value = settings.groq_voice;
  groqVoiceStyle.value = settings.groq_voice_style;
  elevenlabsVoiceId.value = settings.elevenlabs_voice_id;
  elevenlabsModel.value = settings.elevenlabs_model;
  elevenlabsSpeed.value = settings.elevenlabs_speed;
  elevenlabsVolume.value = settings.elevenlabs_volume_percent;
  speakerPreroll.value = settings.speaker_preroll_ms;
  jawActivity.value = settings.jaw_activity_percent;
  document.querySelector("#local-speed-value").textContent = localSpeed.value;
  document.querySelector("#local-pitch-value").textContent = localPitch.value;
  document.querySelector("#local-gap-value").textContent = localGap.value;
  document.querySelector("#elevenlabs-speed-value").textContent = `${Number(elevenlabsSpeed.value).toFixed(2)}×`;
  document.querySelector("#elevenlabs-volume-value").textContent = `${elevenlabsVolume.value}%`;
  document.querySelector("#speaker-preroll-value").textContent = `${speakerPreroll.value} ms`;
  renderJawActivity();
  groqKeyStatus.textContent = body.groq.key_configured ? "key saved" : "not saved";
  elevenlabsKeyStatus.textContent = body.elevenlabs.key_configured ? "key saved" : "not saved";
  providerWarning.textContent = body.cloud_usage_warning;
  updateProviderHelp();
}

async function refreshProviderStatus() {
  renderProviderStatus(await request("/api/providers/status"));
}

async function refreshBrainStatus() {
  renderBrainStatus(await request("/api/brain/status"));
}

function renderManualResult(body) {
  const spoken = body.speech?.spoken;
  brainResult.textContent = spoken
    ? `Sent through Skelly: “${body.spoken_response}”`
    : `Response ready, but audio could not play: ${body.speech?.error || "speaker unavailable"}`;
}

function operationSettingsPayload() {
  return {
    hardware_profile: hardwareProfile.value,
    default_mode: defaultOperationMode.value,
    auto_start: autoStartOperation.checked && defaultOperationMode.value !== "idle",
    device_configured: currentOperationSettings?.device_configured !== false,
    control_address: currentOperationSettings?.control_address ?? null,
    speaker_address: currentOperationSettings?.speaker_address ?? null,
    allow_fpp_override: hardwareProfile.value === "dac" && allowFppOverride.checked,
    manual_camera_enabled: manualCameraEnabled.checked,
    manual_microphone_enabled: manualMicrophoneEnabled.checked,
  };
}

async function saveOperationSettings() {
  return request("/api/operation/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(operationSettingsPayload()),
  });
}

operationSettingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = event.submitter;
  if (submit) submit.disabled = true;
  operationSettingsResult.textContent = "Saving this Pi's operating preferences...";
  try {
    await saveOperationSettings();
    await refreshStatus();
    operationSettingsResult.textContent = "Preferences saved on this Pi.";
  } catch (error) {
    operationSettingsResult.textContent = error.message;
  } finally {
    if (submit) submit.disabled = false;
  }
});

defaultOperationMode.addEventListener("change", () => {
  const idle = defaultOperationMode.value === "idle";
  if (idle) autoStartOperation.checked = false;
  autoStartOperation.disabled = idle;
  startDefaultOperation.textContent = idle
    ? "Remain idle"
    : `Start ${operationModeName(defaultOperationMode.value)}`;
});

hardwareProfile.addEventListener("change", () => {
  renderFppOverrideAvailability(hardwareProfile.value);
});

[manualCameraEnabled, manualMicrophoneEnabled].forEach((control) => {
  control.addEventListener("change", async () => {
    brainVoiceButton.disabled = !manualMicrophoneEnabled.checked;
    try {
      await saveOperationSettings();
      brainResult.textContent = `${control === manualCameraEnabled ? "Camera" : "Microphone"} ${control.checked ? "enabled" : "disabled"}.`;
    } catch (error) {
      brainResult.textContent = error.message;
    }
  });
});

async function startSelectedOperation(selectedMode, button, resultElement = operationResult) {
  const modeName = operationModeName(selectedMode);
  resultElement.textContent = selectedMode === "idle"
    ? "Releasing interaction and motor outputs..."
    : `Preparing ${modeName}...`;
  button.disabled = true;
  document.querySelectorAll("[data-start-operation]").forEach((item) => { item.disabled = true; });
  try {
    const body = selectedMode === "idle"
      ? await request("/api/operation/stop", { method: "POST" })
      : await request("/api/operation/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: selectedMode }),
        });
    renderStatus(body);
    resultElement.textContent = selectedMode === "idle"
      ? "Skelly is safely in standby."
      : `${modeName} is ready.`;
    if (selectedMode === "classic") await refreshMediaFromSkelly();
    if (selectedMode === "ai") await refreshPerceptionStatus();
  } catch (error) {
    resultElement.textContent = error.message;
    await refreshStatus();
    if (operationReady.textContent !== "update required") button.disabled = false;
  }
}

document.querySelectorAll("[data-start-operation]").forEach((button) => {
  button.addEventListener("click", async () => {
    await startSelectedOperation(button.dataset.startOperation, button);
  });
});

startDefaultOperation.addEventListener("click", async () => {
  await startSelectedOperation(
    currentOperationSettings?.default_mode || "ai",
    startDefaultOperation,
    setupStartResult,
  );
});

forgetSkelly.addEventListener("click", () => {
  forgetSkellyResult.textContent = "";
  forgetSkellyDialog.showModal();
});

confirmForgetSkelly.addEventListener("click", async () => {
  confirmForgetSkelly.disabled = true;
  forgetSkellyResult.textContent = "Releasing Skelly and removing the saved speaker pairing...";
  try {
    const body = await request("/api/setup/forget-skelly", { method: "POST" });
    renderStatus(body);
    forgetSkellyDialog.close();
    setupStartResult.textContent = body.warnings?.length
      ? `Skelly was released. ${body.warnings.join(" ")}`
      : "Skelly was released and forgotten by this Pi. Its onboard media was not changed.";
  } catch (error) {
    forgetSkellyResult.textContent = error.message;
  } finally {
    confirmForgetSkelly.disabled = false;
  }
});

stopOperation.addEventListener("click", async () => {
  stopOperation.disabled = true;
  operationResult.textContent = "Stopping interaction and releasing motor outputs...";
  try {
    renderStatus(await request("/api/operation/stop", { method: "POST" }));
    operationResult.textContent = "Skelly is safely in standby.";
  } catch (error) {
    operationResult.textContent = error.message;
  }
});

function renderMediaStatus(body) {
  currentMediaStatus = body;
  speakerVolume.value = String(body.volume ?? 128);
  speakerVolumeValue.textContent = `${Math.round((Number(speakerVolume.value) / 255) * 100)}%`;
  mediaLibrary.replaceChildren();
  const filter = mediaFilter.value.trim().toLowerCase();
  const files = (body.files || []).filter((file) => !filter || String(file.name || "").toLowerCase().includes(filter));
  if (!files.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = filter ? "No stored files match that filter." : body.available
      ? "No media files reported yet. Press Refresh media list."
      : "Connect the prop and start Classic mode first.";
    mediaLibrary.append(empty);
    return;
  }
  const table = document.createElement("table");
  table.className = "media-table";
  const head = document.createElement("thead");
  head.innerHTML = "<tr><th>On</th><th>Name</th><th>Head light</th><th>Torso light</th><th>Movement</th><th>Eye</th><th>Actions</th></tr>";
  const bodyRows = document.createElement("tbody");
  files.forEach((file) => {
    const row = document.createElement("tr");
    const enabledCell = document.createElement("td");
    const enabled = document.createElement("input");
    enabled.type = "checkbox";
    enabled.checked = file.enabled !== false;
    enabled.addEventListener("change", async () => {
      enabled.disabled = true;
      try {
        renderMediaStatus(await request("/api/media/enabled", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ serial: Number(file.serial), enabled: enabled.checked }) }));
      } catch (error) {
        enabled.checked = !enabled.checked;
        enabled.disabled = false;
        mediaResult.textContent = error.message;
      }
    });
    enabledCell.append(enabled);
    const nameCell = document.createElement("td");
    const title = document.createElement("strong");
    title.textContent = file.name || `Media file ${file.serial}`;
    const meta = document.createElement("small");
    meta.className = "muted";
    meta.textContent = `#${file.serial}${file.order ? ` · order ${file.order}` : ""}`;
    nameCell.append(title, meta);
    const lightCell = (light) => {
      const cell = document.createElement("td");
      const dot = document.createElement("span");
      dot.className = "color-dot";
      dot.style.background = light ? `rgb(${light.r}, ${light.g}, ${light.b})` : "#334155";
      dot.title = light ? `Brightness ${light.brightness}` : "No light data";
      cell.append(dot);
      return cell;
    };
    const movement = document.createElement("td");
    const movementNames = { 0: "None", 1: "Head", 2: "Arm", 4: "Torso", 6: "Torso + arm", 7: "Head + arm + torso", 255: "All" };
    movement.textContent = movementNames[file.action] || `Action ${file.action}`;
    const eye = document.createElement("td");
    const eyeImage = document.createElement("img");
    eyeImage.className = "media-eye";
    eyeImage.src = `/static/eye_icon_${file.eye || 1}.png`;
    eyeImage.alt = `Eye ${file.eye || 1}`;
    eye.append(eyeImage, document.createTextNode(String(file.eye || 1)));
    const actions = document.createElement("td");
    actions.className = "media-actions";
    const play = document.createElement("button");
    play.type = "button";
    play.className = "secondary";
    const playing = Number(body.playing_serial) === Number(file.serial);
    play.textContent = playing ? "■ Stop" : "▶ Play";
    play.addEventListener("click", async () => {
      play.disabled = true;
      mediaResult.textContent = playing ? `Stopping ${title.textContent}...` : `Playing ${title.textContent}...`;
      try {
        renderMediaStatus(await request("/api/media/play", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ serial: Number(file.serial), enabled: !playing }),
        }));
        mediaResult.textContent = playing ? "Playback stopped." : `${title.textContent} is playing on Skelly.`;
      } catch (error) {
        mediaResult.textContent = error.message;
        play.disabled = false;
      }
    });
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "secondary";
    edit.textContent = "Edit";
    edit.addEventListener("click", () => openMediaEditor(file));
    actions.append(play, edit);
    row.append(enabledCell, nameCell, lightCell(file.lights?.[1]), lightCell(file.lights?.[0]), movement, eye, actions);
    bodyRows.append(row);
  });
  table.append(head, bodyRows);
  mediaLibrary.append(table);
}

async function refreshMediaStatus() {
  const body = await request("/api/media/status");
  renderMediaStatus(body);
  return body;
}

async function refreshMediaFromSkelly() {
  refreshMedia.disabled = true;
  mediaResult.textContent = "Reading the media list from Skelly...";
  try {
    const body = await request("/api/media/refresh", { method: "POST" });
    renderMediaStatus(body);
    mediaResult.textContent = `${body.file_count} media file${body.file_count === 1 ? "" : "s"} found.`;
    return body;
  } finally {
    refreshMedia.disabled = false;
  }
}

refreshMedia.addEventListener("click", async () => {
  try {
    await refreshMediaFromSkelly();
  } catch (error) {
    mediaResult.textContent = error.message;
  }
});

mediaFilter.addEventListener("input", () => {
  if (currentMediaStatus) renderMediaStatus(currentMediaStatus);
});

addMedia.addEventListener("click", () => mediaFileInput.click());
mediaFileInput.addEventListener("change", async () => {
  const file = mediaFileInput.files?.[0];
  if (!file) return;
  addMedia.disabled = true;
  mediaResult.textContent = `Uploading ${file.name} over Bluetooth. Keep Skelly powered on...`;
  try {
    const response = await fetch(`/api/media/upload?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      headers: { "Content-Type": "audio/mpeg" },
      body: file,
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || `Upload failed (${response.status})`);
    renderMediaStatus(body);
    mediaResult.textContent = `${file.name} was saved on Skelly.`;
  } catch (error) {
    mediaResult.textContent = error.message;
  } finally {
    addMedia.disabled = false;
    mediaFileInput.value = "";
  }
});

function rgbToHex(light, fallback = "#ffffff") {
  if (!light) return fallback;
  return `#${[light.r, light.g, light.b].map((value) => Number(value || 0).toString(16).padStart(2, "0")).join("")}`;
}

function editLightValues(name) {
  const block = document.querySelector(`[data-edit-light="${name}"]`);
  const hex = block.querySelector(".edit-light-color").value.slice(1);
  return {
    brightness: Number(block.querySelector(".edit-light-brightness").value),
    r: parseInt(hex.slice(0, 2), 16),
    g: parseInt(hex.slice(2, 4), 16),
    b: parseInt(hex.slice(4, 6), 16),
    effect_mode: Number(block.querySelector(".edit-light-mode").value),
    cycle: block.querySelector(".edit-light-cycle").checked,
  };
}

function openMediaEditor(file) {
  document.querySelector("#media-editor-title").textContent = file.name || `Media file ${file.serial}`;
  document.querySelector("#media-edit-serial").value = file.serial;
  document.querySelector("#media-edit-action").value = String(file.action ?? 0);
  document.querySelector("#media-edit-eye").value = String(file.eye || 1);
  [["head", file.lights?.[1], "#00ff62"], ["torso", file.lights?.[0], "#3300ff"]].forEach(([name, light, fallback]) => {
    const block = document.querySelector(`[data-edit-light="${name}"]`);
    block.querySelector(".edit-light-color").value = rgbToHex(light, fallback);
    block.querySelector(".edit-light-brightness").value = String(light?.brightness ?? 200);
    block.querySelector(".edit-light-mode").value = String(light?.effect_mode ?? 1);
    block.querySelector(".edit-light-cycle").checked = Boolean(light?.cycle);
  });
  mediaEditorResult.textContent = "";
  mediaEditor.showModal();
}

document.querySelector("#close-media-editor").addEventListener("click", () => mediaEditor.close());
mediaEditorForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = document.querySelector("#save-media-preset");
  submit.disabled = true;
  mediaEditorResult.textContent = "Saving the preset to Skelly...";
  try {
    const body = await request("/api/media/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        serial: Number(document.querySelector("#media-edit-serial").value),
        action: Number(document.querySelector("#media-edit-action").value),
        eye: Number(document.querySelector("#media-edit-eye").value),
        head_light: editLightValues("head"),
        torso_light: editLightValues("torso"),
      }),
    });
    renderMediaStatus(body);
    mediaEditorResult.textContent = "Preset saved.";
    setTimeout(() => mediaEditor.close(), 500);
  } catch (error) {
    mediaEditorResult.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

document.querySelectorAll(".apply-light").forEach((button) => {
  button.addEventListener("click", async () => {
    const block = button.closest("[data-light-channel]");
    const hex = block.querySelector(".light-color").value.slice(1);
    button.disabled = true;
    hardwareResult.textContent = "Applying light settings...";
    try {
      await request("/api/hardware/lighting", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          channel: Number(block.dataset.lightChannel),
          brightness: Number(block.querySelector(".light-brightness").value),
          r: parseInt(hex.slice(0, 2), 16),
          g: parseInt(hex.slice(2, 4), 16),
          b: parseInt(hex.slice(4, 6), 16),
          effect_mode: Number(block.querySelector(".light-mode").value),
          cycle: block.querySelector(".light-cycle").checked,
        }),
      });
      hardwareResult.textContent = "Light settings applied.";
    } catch (error) {
      hardwareResult.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
});

operatorGestureButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    const requestId = ++gestureRequestId;
    const gesture = button.dataset.operatorGesture;
    operatorGestureButtons.forEach((control) => { control.disabled = true; });
    gestureResult.textContent = gesture === "laugh"
      ? "Performing the local Laugh preset..."
      : `Performing ${button.textContent.trim()}...`;
    try {
      const body = await request("/api/operator/gesture", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gesture }),
      });
      if (requestId !== gestureRequestId) return;
      if (gesture === "laugh") {
        const source = body.audio?.source === "skelly_media"
          ? body.audio.name
          : "the Pi's offline voice";
        gestureResult.textContent = `Laugh completed using ${source}${body.dac_used ? " with jaw animation" : ""}.`;
      } else {
        gestureResult.textContent = `${button.textContent.trim()} completed.`;
      }
    } catch (error) {
      if (requestId === gestureRequestId) gestureResult.textContent = error.message;
    } finally {
      if (requestId === gestureRequestId) await refreshStatus();
    }
  });
});

stopOperatorGesture.addEventListener("click", async () => {
  ++gestureRequestId;
  stopOperatorGesture.disabled = true;
  gestureResult.textContent = "Stopping the active gesture and closing the jaw...";
  try {
    await request("/api/operator/gesture/stop", { method: "POST" });
    gestureResult.textContent = "Gesture stopped; jaw close command sent.";
  } catch (error) {
    gestureResult.textContent = error.message;
  } finally {
    await refreshStatus();
  }
});

speakerVolume.addEventListener("input", () => {
  speakerVolumeValue.textContent = `${Math.round((Number(speakerVolume.value) / 255) * 100)}%`;
});

speakerVolume.addEventListener("change", async () => {
  speakerVolume.disabled = true;
  speakerVolumeResult.textContent = "Setting Skelly's speaker volume...";
  try {
    renderMediaStatus(await request("/api/media/volume", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ volume: Number(speakerVolume.value) }),
    }));
    speakerVolumeResult.textContent = `Volume set to ${speakerVolumeValue.textContent}.`;
  } catch (error) {
    speakerVolumeResult.textContent = error.message;
  } finally {
    speakerVolume.disabled = false;
  }
});

document.querySelector("#run-diagnostics").addEventListener("click", async (event) => {
  event.currentTarget.disabled = true;
  diagnostics.textContent = "Running hardware checks…";
  try {
    diagnostics.textContent = JSON.stringify(await request("/api/diagnostics"), null, 2);
  } catch (error) {
    diagnostics.textContent = error.message;
  } finally {
    event.currentTarget.disabled = false;
  }
});

document.querySelectorAll("[data-hardware-action]").forEach((button) => {
  button.addEventListener("click", async () => {
    button.disabled = true;
    hardwareResult.textContent = "Sending hardware command...";
    try {
      const options = { method: "POST", headers: { "Content-Type": "application/json" } };
      if (button.dataset.body) options.body = button.dataset.body;
      await request(button.dataset.hardwareAction, options);
      await refreshStatus();
      hardwareResult.textContent = button.dataset.success || "Hardware command accepted.";
    } catch (error) {
      hardwareResult.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
});

const factoryEyeNames = [
  "Blue", "Hazel", "Green", "Brown", "Red", "Gray",
  "Yellow cat", "Orange cat", "Spiral", "Fire", "Star", "Skull",
  "Fireworks", "American flag", "Hearts", "Clover", "Snowflake", "Confetti",
];

for (let index = 1; index <= 18; index += 1) {
  document.querySelector("#media-edit-eye").append(new Option(`${index} · ${factoryEyeNames[index - 1]}`, String(index)));
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary eye-choice";
  button.title = `Set ${factoryEyeNames[index - 1]} eyes`;
  const thumbnail = document.createElement("img");
  thumbnail.src = `/static/eye_icon_${index}.png`;
  thumbnail.alt = "";
  const eyeLabel = document.createElement("span");
  eyeLabel.textContent = factoryEyeNames[index - 1];
  const eyeNumber = document.createElement("small");
  eyeNumber.textContent = String(index);
  button.replaceChildren(thumbnail, eyeLabel, eyeNumber);
  button.addEventListener("click", async () => {
    button.disabled = true;
    hardwareResult.textContent = `Setting factory eye icon ${index}...`;
    try {
      await request("/api/hardware/eye-index", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index }),
      });
      await refreshStatus();
      hardwareResult.textContent = `Factory eye icon ${index} selected.`;
    } catch (error) {
      hardwareResult.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  document.querySelector("#eye-index-controls").append(button);
}

document.querySelector("#hardware-discover").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  hardwareDiscovery.textContent = "Scanning nearby BLE devices for eight seconds...";
  try {
    const body = await request("/api/hardware/discover", { method: "POST" });
    if (!body.devices.length) {
      hardwareDiscovery.textContent = "No Skelly or Lily device was found.";
    } else {
      hardwareAddress.value = body.devices[0].address;
      hardwareDiscovery.textContent = body.devices
        .map((item) => `${item.name} - ${item.address} (${item.rssi} dBm)`)
        .join(" | ");
    }
  } catch (error) {
    hardwareDiscovery.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

async function discoverSetupDevices() {
  setupRescanDevice.disabled = true;
  setupConnectDevice.disabled = true;
  setupDeviceSelect.replaceChildren(new Option("Scanning nearby props…", ""));
  setupDiscoveryResult.textContent = "Scanning for compatible Skelly and Lily controllers for eight seconds…";
  try {
    const body = await request("/api/hardware/discover", { method: "POST" });
    setupDeviceSelect.replaceChildren();
    if (!body.devices.length) {
      setupDeviceSelect.append(new Option("No compatible prop found", ""));
      setupDiscoveryResult.textContent = "Nothing was found. Confirm the prop is powered on, then scan again.";
      return;
    }
    body.devices.forEach((device) => {
      const signal = Number.isFinite(device.rssi) ? ` · ${device.rssi} dBm` : "";
      setupDeviceSelect.append(new Option(`${device.name} · ${device.address}${signal}`, device.address));
    });
    hardwareAddress.value = setupDeviceSelect.value;
    setupConnectDevice.disabled = false;
    setupDiscoveryResult.textContent = body.devices.length === 1
      ? "One compatible prop found. Select Connect to save it to this Pi."
      : `${body.devices.length} compatible props found. Choose the correct one before connecting.`;
  } catch (error) {
    setupDeviceSelect.replaceChildren(new Option("Bluetooth scan unavailable", ""));
    setupDiscoveryResult.textContent = error.message;
  } finally {
    setupRescanDevice.disabled = false;
  }
}

setupDeviceSelect.addEventListener("change", () => {
  hardwareAddress.value = setupDeviceSelect.value;
  setupConnectDevice.disabled = !setupDeviceSelect.value;
});

setupRescanDevice.addEventListener("click", discoverSetupDevices);

setupConnectDevice.addEventListener("click", async () => {
  if (!setupDeviceSelect.value) return;
  hardwareAddress.value = setupDeviceSelect.value;
  await connectToSkelly(setupConnectDevice, setupDiscoveryResult);
});

async function connectToSkelly(button, resultElement) {
  button.disabled = true;
  resultElement.textContent = "Connecting to Skelly over Bluetooth...";
  try {
    await request("/api/hardware/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address: hardwareAddress.value.trim() || null }),
    });
    await refreshStatus();
    resultElement.textContent = "Skelly connected. Motors remain safely disarmed until a mode starts.";
    if (resultElement !== hardwareResult) hardwareResult.textContent = "BLE connected. Motors remain disarmed.";
  } catch (error) {
    resultElement.textContent = error.message;
  } finally {
    if (headerPropStatus.textContent !== "connected") button.disabled = false;
  }
}

topConnectSkelly.addEventListener("click", async () => {
  if (topConnectSkelly.dataset.connected !== "true") {
    await connectToSkelly(topConnectSkelly, topConnectResult);
    return;
  }
  topConnectSkelly.disabled = true;
  topConnectResult.textContent = "Disconnecting Skelly...";
  try {
    await request("/api/hardware/disconnect", { method: "POST" });
    topConnectResult.textContent = "Skelly disconnected.";
    await refreshStatus();
  } catch (error) {
    topConnectResult.textContent = error.message;
  } finally {
    topConnectSkelly.disabled = false;
  }
});

document.querySelector("#hardware-connect").addEventListener("click", async (event) => {
  await connectToSkelly(event.currentTarget, hardwareResult);
});

document.querySelector("#hardware-disconnect").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await request("/api/hardware/disconnect", { method: "POST" });
    await refreshStatus();
    hardwareResult.textContent = "BLE disconnected.";
  } catch (error) {
    hardwareResult.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

speakerConnect.addEventListener("click", async () => {
  speakerConnect.disabled = true;
  speakerResult.textContent = "Enabling Live Mode and connecting the Skelly speaker...";
  try {
    const audio = await request("/api/audio/prepare-connect", { method: "POST" });
    renderAudioStatus(audio);
    speakerResult.textContent = audio.sink_ready
      ? "Skelly speaker connected and selected for Pi audio."
      : audio.last_error || "Speaker connected, but its Pi audio route is not ready yet.";
    await refreshStatus();
  } catch (error) {
    speakerResult.textContent = `${error.message}. Confirm BLE prop control is connected and the speaker was paired once.`;
    await refreshAudioStatus().catch(() => {});
  }
});

speakerDisconnect.addEventListener("click", async () => {
  speakerDisconnect.disabled = true;
  speakerResult.textContent = "Disconnecting the Skelly speaker...";
  try {
    const audio = await request("/api/audio/disconnect", { method: "POST" });
    renderAudioStatus(audio);
    speakerResult.textContent = "Skelly speaker disconnected.";
    await refreshStatus();
  } catch (error) {
    speakerResult.textContent = error.message;
    await refreshAudioStatus().catch(() => {});
  }
});

dacArm.addEventListener("click", async () => {
  dacArm.disabled = true;
  dacResult.textContent = "Arming DAC safety interlock; no packet is sent yet...";
  try {
    await request("/api/dac/arm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true }),
    });
    await refreshStatus();
    dacResult.textContent = "DAC armed. A deliberate slider or center command will start E1.31 output.";
  } catch (error) {
    dacResult.textContent = error.message;
    dacArm.disabled = false;
  }
});

dacRelease.addEventListener("click", async () => {
  dacRelease.disabled = true;
  try {
    await request("/api/dac/release", { method: "POST" });
    await refreshStatus();
    dacResult.textContent = "DAC stream released for xLights/FPP.";
  } catch (error) {
    dacResult.textContent = error.message;
  } finally {
    dacRelease.disabled = false;
  }
});

dacCenter.addEventListener("click", async () => {
  dacCenter.disabled = true;
  dacResult.textContent = "Sending the configured center positions and closing the jaw...";
  try {
    await request("/api/dac/center", { method: "POST" });
    await refreshStatus();
    dacResult.textContent = "Configured center positions are streaming.";
  } catch (error) {
    dacResult.textContent = error.message;
  } finally {
    await refreshStatus();
  }
});

async function setJaw(open) {
  dacJawOpen.disabled = true;
  dacJawClose.disabled = true;
  const value = open ? 255 : 0;
  dacResult.textContent = open ? "Opening jaw..." : "Closing jaw...";
  try {
    await request("/api/dac/position", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jaw: value }),
    });
    dacResult.textContent = open ? "Jaw is open." : "Jaw is closed.";
  } catch (error) {
    dacResult.textContent = error.message;
  } finally {
    await refreshStatus();
  }
}

dacJawOpen.addEventListener("click", () => setJaw(true));
dacJawClose.addEventListener("click", () => setJaw(false));

Object.entries(dacSliders).forEach(([name, slider]) => {
  slider.addEventListener("input", () => {
    dacValueOutputs[name].textContent = slider.value;
  });
  slider.addEventListener("change", async () => {
    slider.disabled = true;
    const value = Number(slider.value);
    dacResult.textContent = `Sending ${name} value ${value}...`;
    try {
      await request("/api/dac/position", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [name]: value }),
      });
      dacResult.textContent = `${name} is streaming at ${value}.`;
    } catch (error) {
      dacResult.textContent = error.message;
    } finally {
      await refreshStatus();
    }
  });
});

document.querySelector("#elevenlabs-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = event.currentTarget.querySelector("button[type='submit']");
  const apiKeyInput = document.querySelector("#elevenlabs-api-key");
  submitButton.disabled = true;
  elevenlabsResult.textContent = "Validating with ElevenLabs…";
  try {
    const payload = { api_key: apiKeyInput.value };
    await request("/api/setup/elevenlabs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    apiKeyInput.value = "";
    await refreshStatus();
    await refreshProviderStatus();
    elevenlabsResult.textContent = "Key validated and saved locally for text-to-speech.";
  } catch (error) {
    elevenlabsResult.textContent = error.message;
  } finally {
    submitButton.disabled = false;
  }
});

document.querySelectorAll("[data-provider-preset]").forEach((button) => {
  button.addEventListener("click", () => {
    const preset = button.dataset.providerPreset;
    if (preset === "offline") {
      brainProvider.value = "local";
      voiceProvider.value = "local";
    } else if (preset === "cloud") {
      brainProvider.value = "groq";
      voiceProvider.value = "groq";
      groqVoice.value = "troy";
      groqVoiceStyle.value = "cartoon_skeleton_villain";
    } else {
      brainProvider.value = "groq";
      voiceProvider.value = "elevenlabs";
      elevenlabsModel.value = "eleven_v3";
      elevenlabsSpeed.value = "0.85";
      elevenlabsVolume.value = "85";
      jawActivity.value = "35";
    }
    updateProviderHelp();
    providerResult.textContent = "Preset selected. Save the choices to activate it.";
  });
});

copyVoicePrompt.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(voiceDesignPrompt.value);
  } catch {
    voiceDesignPrompt.select();
    document.execCommand("copy");
    window.getSelection()?.removeAllRanges();
  }
  copyVoicePromptResult.textContent = "Voice Design prompt copied.";
});

[brainProvider, voiceProvider, elevenlabsModel].forEach((control) => {
  control.addEventListener("change", updateProviderHelp);
});

[
  [localSpeed, "#local-speed-value", ""],
  [localPitch, "#local-pitch-value", ""],
  [localGap, "#local-gap-value", ""],
  [elevenlabsSpeed, "#elevenlabs-speed-value", "×"],
  [elevenlabsVolume, "#elevenlabs-volume-value", "%"],
  [speakerPreroll, "#speaker-preroll-value", " ms"],
].forEach(([control, outputSelector, suffix]) => {
  control.addEventListener("input", () => {
    document.querySelector(outputSelector).textContent = `${control.value}${suffix}`;
  });
});

function renderJawActivity() {
  const value = Number(jawActivity.value);
  const description = value === 0
    ? "off"
    : value <= 35
      ? "calm"
      : value <= 70
        ? "balanced"
        : "lively";
  document.querySelector("#jaw-activity-value").textContent = `${value}% · ${description}`;
}

jawActivity.addEventListener("input", renderJawActivity);

async function saveProviderChoices() {
  return request("/api/providers/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(providerPayload()),
  });
}

providerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = event.submitter;
  if (submit) submit.disabled = true;
  providerResult.textContent = "Saving AI and voice choices...";
  try {
    await saveProviderChoices();
    await refreshProviderStatus();
    await refreshBrainStatus();
    providerResult.textContent = "AI and voice choices saved. Conversation context was reset.";
  } catch (error) {
    providerResult.textContent = error.message;
  } finally {
    if (submit) submit.disabled = false;
  }
});

previewVoice.addEventListener("click", async () => {
  previewVoice.disabled = true;
  providerResult.textContent = `Preparing ${voiceProvider.value} voice preview...`;
  try {
    await saveProviderChoices();
    const body = await request("/api/voice/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "Welcome, brave visitor. Skelly is awake!" }),
    });
    const tuning = body.voice_model
      ? `; speed ${body.voice_speed}×; volume ${body.voice_volume_percent}%`
      : "";
    providerResult.textContent = `Confirmed ${body.voice_provider} voice: ${body.engine}${tuning}; Bluetooth wake-up ${body.speaker_preroll_ms} ms.`;
  } catch (error) {
    providerResult.textContent = `Selected voice could not play: ${error.message}`;
  } finally {
    previewVoice.disabled = false;
  }
});

document.querySelector("#groq-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = event.currentTarget.querySelector("button[type='submit']");
  const key = document.querySelector("#groq-api-key");
  submit.disabled = true;
  groqResult.textContent = "Validating the key without generating anything...";
  try {
    await request("/api/setup/groq", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key.value }),
    });
    key.value = "";
    await refreshStatus();
    await refreshProviderStatus();
    groqResult.textContent = "Groq key validated and saved only on this Pi.";
  } catch (error) {
    groqResult.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

document.querySelector("#analyze-camera").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  cameraResult.textContent = "Capturing and analyzing locally…";
  try {
    const response = await fetch(`/api/sensors/camera/frame.jpg?t=${Date.now()}`);
    if (!response.ok) {
      const body = await response.json();
      throw new Error(body.detail || `Camera analysis failed (${response.status})`);
    }
    const image = await response.blob();
    if (cameraObjectUrl) URL.revokeObjectURL(cameraObjectUrl);
    cameraObjectUrl = URL.createObjectURL(image);
    cameraFrame.src = cameraObjectUrl;
    cameraFrame.hidden = false;
    cameraPlaceholder.hidden = true;
    await refreshSensorStatus();
    cameraResult.textContent = "Frame analyzed locally on the Pi.";
  } catch (error) {
    cameraResult.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#sample-microphone").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  microphoneResult.textContent = "Recording one second locally—speak now…";
  try {
    renderSensorStatus(await request("/api/sensors/microphone/sample", { method: "POST" }));
    microphonePlayback.src = `/api/sensors/microphone/last.wav?t=${Date.now()}`;
    microphonePlayback.hidden = false;
    microphoneResult.textContent = "Sample analyzed. Press play to verify microphone quality.";
  } catch (error) {
    microphoneResult.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

transcribeMicrophone.addEventListener("click", async () => {
  transcribeMicrophone.disabled = true;
  microphoneResult.textContent = "Recording five seconds—speak a complete sentence now…";
  try {
    const body = await request("/api/sensors/microphone/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ duration_seconds: 5 }),
    });
    renderSensorStatus(body);
    microphonePlayback.src = `/api/sensors/microphone/last.wav?t=${Date.now()}`;
    microphonePlayback.hidden = false;
    microphoneResult.textContent = "Speech transcribed entirely on the Pi.";
  } catch (error) {
    microphoneResult.textContent = error.message;
  } finally {
    transcribeMicrophone.disabled = false;
  }
});

startPerception.addEventListener("click", async () => {
  startPerception.disabled = true;
  perceptionResult.textContent = "Preparing AI Mode...";
  try {
    const body = await request("/api/operation/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "ai" }),
    });
    renderStatus(body);
    await refreshPerceptionStatus();
    perceptionResult.textContent = "AI Mode is watching for a visitor. Speak naturally after you are detected.";
  } catch (error) {
    perceptionResult.textContent = error.message;
    startPerception.disabled = false;
  }
});

stopPerception.addEventListener("click", async () => {
  stopPerception.disabled = true;
  perceptionResult.textContent = "Stopping AI Mode...";
  try {
    renderStatus(await request("/api/operation/stop", { method: "POST" }));
    await refreshPerceptionStatus();
    perceptionResult.textContent = "AI Mode stopped.";
  } catch (error) {
    perceptionResult.textContent = error.message;
  }
});

document.querySelector("#clear-perception-events").addEventListener("click", async () => {
  try {
    renderPerceptionStatus(await request("/api/perception/events/clear", { method: "POST" }));
    perceptionResult.textContent = "Local event log cleared.";
  } catch (error) {
    perceptionResult.textContent = error.message;
  }
});

brainTestForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  brainBusy = true;
  brainTestButton.disabled = true;
  brainVoiceButton.disabled = true;
  brainResult.textContent = "Sending the operator's line to Skelly...";
  try {
    const body = await request("/api/operator/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: brainTestInput.value }),
    });
    renderManualResult(body);
    brainTestInput.value = "";
    await refreshStatus();
  } catch (error) {
    brainResult.textContent = error.message;
  } finally {
    brainBusy = false;
    brainTestButton.disabled = false;
    brainVoiceButton.disabled = !manualMicrophoneEnabled.checked;
  }
});

async function captureOperatorCameraSnapshot() {
  if (!manualCameraEnabled.checked) {
    operatorCameraResult.textContent = "Camera is disabled in Operator Mode.";
    return false;
  }
  operatorCameraResult.textContent = "Capturing what the visitor camera sees...";
  try {
    const response = await fetch(`/api/sensors/camera/frame.jpg?t=${Date.now()}`);
    if (!response.ok) {
      const body = await response.json();
      throw new Error(body.detail || `Camera snapshot failed (${response.status})`);
    }
    const image = await response.blob();
    if (operatorCameraObjectUrl) URL.revokeObjectURL(operatorCameraObjectUrl);
    operatorCameraObjectUrl = URL.createObjectURL(image);
    operatorCameraFrame.src = operatorCameraObjectUrl;
    operatorCameraFrame.hidden = false;
    operatorCameraPlaceholder.hidden = true;
    operatorCameraResult.textContent = "Snapshot captured when listening began.";
    return true;
  } catch (error) {
    operatorCameraResult.textContent = `Snapshot unavailable: ${error.message}`;
    return false;
  }
}

async function performOperatorListeningPose() {
  if (!operatorListenGestureAvailable) return false;
  try {
    await request("/api/operator/gesture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gesture: "listen" }),
    });
    return true;
  } catch (error) {
    gestureResult.textContent = `Listening pose unavailable: ${error.message}`;
    return false;
  }
}

brainVoiceButton.addEventListener("click", async () => {
  brainBusy = true;
  brainVoiceButton.disabled = true;
  brainTestButton.disabled = true;
  brainResult.textContent = "Capturing the visitor and recording for five seconds...";
  const snapshotPromise = captureOperatorCameraSnapshot();
  const listeningPosePromise = performOperatorListeningPose();
  try {
    const body = await request("/api/sensors/microphone/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ duration_seconds: 5 }),
    });
    const [snapshotCaptured, listeningPoseUsed] = await Promise.all([
      snapshotPromise,
      listeningPosePromise,
    ]);
    const microphone = body.microphone || {};
    brainHeardText.textContent = microphone.transcript || "No sentence recognized.";
    const capturedNote = snapshotCaptured ? " Camera snapshot captured." : "";
    const poseNote = listeningPoseUsed ? " Listening pose sent." : "";
    brainResult.textContent = microphone.transcript
      ? "Visitor transcript captured for the operator. Skelly did not answer automatically."
      : "No visitor sentence was recognized; try again.";
    brainResult.textContent += capturedNote + poseNote;
    await refreshStatus();
  } catch (error) {
    await Promise.all([snapshotPromise, listeningPosePromise]);
    brainResult.textContent = error.message;
  } finally {
    brainBusy = false;
    brainVoiceButton.disabled = !manualMicrophoneEnabled.checked;
    brainTestButton.disabled = false;
  }
});

brainResetButton.addEventListener("click", async () => {
  brainBusy = true;
  brainResetButton.disabled = true;
  try {
    brainHeardText.textContent = "No voice question recorded yet.";
    brainResult.textContent = "Visitor transcript cleared.";
  } catch (error) {
    brainResult.textContent = error.message;
  } finally {
    brainBusy = false;
    brainResetButton.disabled = false;
  }
});

function renderUpdateStatus(body) {
  updateVersion.textContent = `version ${body.current_version}`;
  updateVersion.classList.toggle("neutral", !body.update_available);
  updateResult.textContent = body.message;
  installUpdate.hidden = !body.update_available || !body.installable;
  installUpdate.dataset.version = body.latest_version || "";
  downloadUpdate.hidden = !body.update_available || !body.release_notes_url;
  if (!downloadUpdate.hidden) {
    downloadUpdate.href = body.release_notes_url;
    downloadUpdate.textContent = "View release notes";
  }
  updateAvailableBadge.hidden = !body.update_available;
  if (body.update_available) updateAvailableBadge.textContent = `USA ${body.latest_version} available`;
  const installation = body.installation || {};
  if (["downloading", "staged", "installing"].includes(installation.state)) {
    updateResult.textContent = installation.message || "Installing update…";
    installUpdate.disabled = true;
    checkForUpdates.disabled = true;
    monitorUpdateInstallation();
  } else if (installation.state === "failed" || installation.state === "succeeded") {
    updateResult.textContent = installation.message || body.message;
  }
}

async function refreshUpdateStatus(check = false) {
  const body = await request(check ? "/api/update/check" : "/api/update/status", {
    method: check ? "POST" : "GET",
  });
  renderUpdateStatus(body);
}

checkForUpdates.addEventListener("click", async () => {
  checkForUpdates.disabled = true;
  updateResult.textContent = "Checking the configured release channel...";
  try {
    await refreshUpdateStatus(true);
  } catch (error) {
    updateResult.textContent = error.message;
  } finally {
    checkForUpdates.disabled = false;
  }
});

updateAvailableBadge.addEventListener("click", () => {
  selectDashboardTab("diagnostics");
  document.querySelector("#software-update-section").scrollIntoView({ behavior: "smooth" });
});

async function monitorUpdateInstallation() {
  if (updateMonitorActive) return;
  updateMonitorActive = true;
  try {
    for (let attempt = 0; attempt < 600; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      try {
        const status = await request("/api/update/install-status");
        updateResult.textContent = status.message || "Installing update…";
        if (status.state === "succeeded") {
          installUpdate.disabled = true;
          checkForUpdates.disabled = false;
          updateAvailableBadge.hidden = true;
          setTimeout(() => window.location.reload(), 1800);
          return;
        }
        if (status.state === "failed") {
          installUpdate.disabled = false;
          checkForUpdates.disabled = false;
          return;
        }
      } catch {
        // The dashboard briefly disappears while the updated service restarts.
        updateResult.textContent = "USA is restarting to finish the update…";
      }
    }
    updateResult.textContent = "The update is still running. Reopen Diagnostics to check its status.";
    checkForUpdates.disabled = false;
  } finally {
    updateMonitorActive = false;
  }
}

installUpdate.addEventListener("click", async () => {
  const version = installUpdate.dataset.version || "the new release";
  if (!window.confirm(`Install USA ${version} now? The dashboard will restart automatically.`)) return;
  installUpdate.disabled = true;
  checkForUpdates.disabled = true;
  updateResult.textContent = `Downloading and verifying USA ${version}…`;
  try {
    const status = await request("/api/update/install", { method: "POST" });
    updateResult.textContent = status.message || "The verified update is starting…";
    await monitorUpdateInstallation();
  } catch (error) {
    updateResult.textContent = error.message;
    installUpdate.disabled = false;
    checkForUpdates.disabled = false;
  }
});

async function refreshSshStatus() {
  try {
    const body = await request("/api/system/ssh");
    sshStatus.textContent = body.enabled ? "enabled" : "disabled";
    sshStatus.classList.toggle("neutral", !body.enabled);
  } catch {
    sshStatus.textContent = "image only";
    sshStatus.classList.add("neutral");
  }
}

document.querySelector("#ssh-enable-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  sshResult.textContent = "Enabling private support access…";
  try {
    const body = await request("/api/system/ssh/enable", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: sshPassword.value, persistent: sshPersistent.checked }),
    });
    sshPassword.value = "";
    sshResult.textContent = body.enabled
      ? `SSH enabled${sshPersistent.checked ? " until disabled" : " for 30 minutes"}. Connect with ssh ${body.username}@${body.hostname}.local`
      : "SSH did not enable.";
    await refreshSshStatus();
  } catch (error) {
    sshResult.textContent = error.message;
  }
});

document.querySelector("#ssh-disable").addEventListener("click", async () => {
  try {
    await request("/api/system/ssh/disable", { method: "POST" });
    sshResult.textContent = "SSH disabled.";
    await refreshSshStatus();
  } catch (error) {
    sshResult.textContent = error.message;
  }
});

async function requestControllerPower(path, message, confirmation = null) {
  if (confirmation && !window.confirm(confirmation)) return;
  controllerPowerResult.textContent = message;
  try {
    const body = await request(path, { method: "POST" });
    controllerPowerResult.textContent = `${body.message}. This page may disconnect briefly.`;
  } catch (error) { controllerPowerResult.textContent = error.message; }
}

document.querySelector("#restart-usa-service").addEventListener("click", () => requestControllerPower(
  "/api/system/service/restart", "Scheduling service restart…",
));
document.querySelector("#reboot-controller").addEventListener("click", () => requestControllerPower(
  "/api/system/reboot", "Scheduling Raspberry Pi reboot…", "Reboot the Raspberry Pi now?",
));
document.querySelector("#shutdown-controller").addEventListener("click", () => requestControllerPower(
  "/api/system/shutdown", "Scheduling safe shutdown…", "Shut down the Raspberry Pi now? You will need to remove and restore power to start it again.",
));

function showOnboardingPhase(phase) {
  onboardingNetworkStep.hidden = phase !== "network";
  onboardingDisclaimerStep.hidden = phase !== "disclaimer";
  if (phase === "pairing") {
    if (onboardingDialog.open) onboardingDialog.close();
    selectDashboardTab("setup");
    firstRunDiscovery.hidden = false;
    if (!firstRunDiscoveryStarted) {
      firstRunDiscoveryStarted = true;
      discoverSetupDevices();
    }
  } else if (["network", "disclaimer"].includes(phase) && !onboardingDialog.open) {
    onboardingDialog.showModal();
  } else if (phase === "complete" && onboardingDialog.open) {
    onboardingDialog.close();
  }
}

function renderWifiNetworks(select, networks) {
  select.replaceChildren(new Option("Choose a network", ""));
  networks.forEach((network) => select.append(
    new Option(`${network.ssid}${network.signal ? ` · ${network.signal}%` : ""}`, network.ssid),
  ));
  if (!networks.length) select.append(new Option("No cached networks — refresh the list", "", true, false));
}

function showControllerLink(result, prefix, suffix = "") {
  const link = document.createElement("a");
  link.href = "http://usa-controller:8787";
  link.textContent = "Open usa-controller:8787";
  result.replaceChildren(
    document.createTextNode(`${prefix} `),
    link,
    document.createTextNode(suffix ? ` ${suffix}` : ""),
  );
}

async function loadWifiNetworks() {
  const scan = await request("/api/onboarding/wifi");
  renderWifiNetworks(onboardingWifiSelect, scan.networks);
  renderWifiNetworks(setupWifiSelect, scan.networks);
  return scan.networks;
}

async function refreshWifiStatus() {
  try {
    const body = await request("/api/system/wifi");
    wifiModeStatus.textContent = body.mode === "hotspot" ? "USA hotspot" : "home WiFi";
    if (body.last_result?.message) setupWifiResult.textContent = body.last_result.message;
  } catch {
    wifiModeStatus.textContent = "image only";
  }
}

async function refreshOnboarding() {
  const body = await request("/api/onboarding/status");
  if (!body.enabled) return;
  showOnboardingPhase(body.phase);
  if (body.phase === "network") {
    try {
      await loadWifiNetworks();
    } catch (error) {
      onboardingNetworkResult.textContent = error.message;
    }
  }
}

document.querySelector("#onboarding-stay-offline").addEventListener("click", async () => {
  onboardingNetworkResult.textContent = "Keeping the USA setup hotspot active…";
  try {
    const body = await request("/api/onboarding/offline", { method: "POST" });
    showOnboardingPhase(body.phase);
  } catch (error) { onboardingNetworkResult.textContent = error.message; }
});

document.querySelector("#onboarding-connect-wifi").addEventListener("click", async () => {
  const ssid = onboardingWifiManual.value.trim() || onboardingWifiSelect.value;
  if (!ssid) {
    onboardingNetworkResult.textContent = "Choose a WiFi network or enter a hidden network name.";
    return;
  }
  onboardingNetworkResult.textContent = "Saving WiFi and moving to your home network…";
  try {
    await request("/api/onboarding/wifi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ssid, password: onboardingWifiPassword.value }),
    });
    showControllerLink(
      onboardingNetworkResult,
      "WiFi saved. After this hotspot closes, join the same home network and",
      ".",
    );
  } catch (error) { onboardingNetworkResult.textContent = error.message; }
});

document.querySelector("#onboarding-refresh-wifi").addEventListener("click", async () => {
  onboardingNetworkResult.textContent = "Refreshing networks. The hotspot will briefly disconnect; reconnect in about 15 seconds…";
  try {
    const body = await request("/api/system/wifi/refresh", { method: "POST" });
    onboardingNetworkResult.textContent = `${body.message}. Reconnect to the USA hotspot in about 15 seconds, then reload this page.`;
  } catch (error) { onboardingNetworkResult.textContent = error.message; }
});

document.querySelector("#setup-wifi-connect").addEventListener("click", async () => {
  const ssid = setupWifiManual.value.trim() || setupWifiSelect.value;
  if (!ssid) {
    setupWifiResult.textContent = "Choose a nearby network or enter a hidden network name.";
    return;
  }
  setupWifiResult.textContent = "Saving WiFi. This page will disconnect while the controller changes networks…";
  try {
    await request("/api/onboarding/wifi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ssid, password: setupWifiPassword.value }),
    });
    showControllerLink(
      setupWifiResult,
      "WiFi saved. After joining the same home network,",
      ". If connection fails, the USA hotspot returns automatically.",
    );
  } catch (error) { setupWifiResult.textContent = error.message; }
});

document.querySelector("#setup-wifi-refresh").addEventListener("click", async () => {
  setupWifiResult.textContent = "Scheduling a fresh scan…";
  try {
    const body = await request("/api/system/wifi/refresh", { method: "POST" });
    setupWifiResult.textContent = `${body.message}. Reconnect in about 10 seconds.`;
  } catch (error) { setupWifiResult.textContent = error.message; }
});

document.querySelector("#setup-wifi-hotspot").addEventListener("click", async () => {
  setupWifiResult.textContent = "Returning to the USA setup hotspot…";
  try {
    await request("/api/system/wifi/hotspot", { method: "POST" });
    setupWifiResult.textContent = "Reconnect to UltraSkellyAdvanced-Setup, then open 192.168.4.1.";
  } catch (error) { setupWifiResult.textContent = error.message; }
});

onboardingAcceptCheck.addEventListener("change", () => {
  onboardingAccept.disabled = !onboardingAcceptCheck.checked;
});

onboardingAccept.addEventListener("click", async () => {
  try {
    const body = await request("/api/onboarding/disclaimer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accepted: true }),
    });
    showOnboardingPhase(body.phase);
  } catch (error) { onboardingDisclaimerResult.textContent = error.message; }
});

onboardingDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
});

refreshStatus();
refreshAudioStatus().catch((error) => {
  speakerResult.textContent = `Speaker status unavailable: ${error.message}`;
});
refreshMediaStatus().catch((error) => {
  speakerVolumeResult.textContent = `Volume status unavailable: ${error.message}`;
});
refreshSensorStatus().catch((error) => {
  cameraResult.textContent = `Sensor status unavailable: ${error.message}`;
});
refreshPerceptionStatus().catch((error) => {
  perceptionResult.textContent = `Visitor monitor unavailable: ${error.message}`;
});
refreshBrainStatus().catch((error) => {
  brainResult.textContent = `Operator voice status unavailable: ${error.message}`;
});
refreshProviderStatus().catch((error) => {
  providerResult.textContent = `Provider setup unavailable: ${error.message}`;
});
refreshUpdateStatus().catch((error) => {
  updateResult.textContent = `Update status unavailable: ${error.message}`;
});
refreshOnboarding().catch(() => {});
refreshSshStatus().catch(() => {});
loadWifiNetworks().catch((error) => { setupWifiResult.textContent = error.message; });
refreshWifiStatus().catch(() => {});
window.setTimeout(() => refreshUpdateStatus(true).catch(() => {}), 60000);
window.setInterval(() => refreshUpdateStatus(true).catch(() => {}), 86400000);
setInterval(refreshStatus, 5000);
setInterval(() => refreshAudioStatus().catch(() => {}), 15000);
setInterval(() => refreshPerceptionStatus().catch(() => {}), 400);
setInterval(() => refreshBrainStatus().catch(() => {}), 5000);
setInterval(pollManualCamera, 1800);
