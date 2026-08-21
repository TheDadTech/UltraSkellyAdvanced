from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "skelly_ai" / "static"


class _DashboardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.tabs: set[str] = set()
        self.panels: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if element_id := attributes.get("id"):
            self.ids.append(element_id)
        if tab := attributes.get("data-dashboard-tab"):
            self.tabs.add(tab)
        if panel := attributes.get("data-dashboard-panel"):
            self.panels.add(panel)


def test_dashboard_has_unique_ids_and_matching_tabs() -> None:
    parser = _DashboardParser()
    parser.feed((STATIC / "index.html").read_text(encoding="utf-8"))

    assert len(parser.ids) == len(set(parser.ids))
    assert parser.tabs == {"operate", "setup", "voice", "diagnostics"}
    assert parser.panels == parser.tabs


def test_all_factory_eye_thumbnails_are_packaged_and_used() -> None:
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert "eye_icon_${index}.png" in script
    for index in range(1, 19):
        eye = STATIC / f"eye_icon_{index}.png"
        assert eye.is_file()
        assert eye.stat().st_size > 0


def test_blue_slate_theme_tokens_are_defined() -> None:
    stylesheet = (STATIC / "styles.css").read_text(encoding="utf-8")

    for token in ("--bg:", "--panel:", "--border:", "--blue:", "--blue-bright:"):
        assert token in stylesheet


def test_finished_product_banner_and_blue_orange_brand_theme_are_packaged() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    stylesheet = (STATIC / "styles.css").read_text(encoding="utf-8")
    banner = STATIC / "ultra-skelly-banner.png"

    assert 'class="product-header"' in html
    assert 'src="/static/ultra-skelly-banner.png"' in html
    assert "ULTRASKELLYADVANCED · A THEDADTECH PROJECT" in html
    assert banner.is_file()
    assert banner.stat().st_size > 1_000_000
    for token in ("--orange:", "--orange-bright:", "--orange-soft:"):
        assert token in stylesheet


def test_provider_controls_and_safe_head_axis_minimums_are_present() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    for element_id in (
        'id="brain-provider"',
        'id="voice-provider"',
        'id="speaker-preroll"',
        'id="interaction-cue"',
        'id="elevenlabs-model"',
        'id="elevenlabs-speed"',
        'id="elevenlabs-volume"',
        'id="groq-form"',
    ):
        assert element_id in html
    for axis in ("dac-tilt", "dac-yaw", "dac-pitch"):
        control = html.split(f'id="{axis}"', 1)[1].split(">", 1)[0]
        assert 'min="1"' in control
        assert 'max="255"' in control

    assert 'href="https://console.groq.com/authenticate"' in html
    assert 'href="https://try.elevenlabs.io/38yj9peuwrb7"' in html
    assert "Required API key permissions" in html
    assert "<strong>Text to Speech:</strong> Access" in html
    assert "<strong>Voices:</strong> Write" in html
    assert "<strong>Models:</strong> Access" in html
    assert "project affiliate link" not in html
    assert 'href="https://elevenlabs.io/affiliates"' not in html
    assert "Preview selected voice only" in html
    assert "Voice ID, not Agent ID" in html
    assert 'id="groq-voice-style"' in html
    assert "Cartoon Skeleton Villain" in html
    assert "accept its model terms" in html
    assert "Prepare and connect speaker" in html
    assert "SPEAK NOW" in (STATIC / "app.js").read_text(encoding="utf-8")


def test_guided_operation_interface_is_present() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    for element_id in (
        'id="operation-settings-form"',
        'id="first-run-discovery"',
        'id="setup-device-select"',
        'id="setup-connect-device"',
        'id="setup-rescan-device"',
        'id="hardware-profile"',
        'id="default-operation-mode"',
        'id="allow-fpp-override"',
        'id="fpp-override-setting"',
        'id="mode-launcher-section"',
        'id="speaker-volume"',
        'id="media-library"',
        'id="pi-status-light"',
        'id="header-speaker-status"',
        'id="top-connect-skelly"',
        'id="saved-skelly-section"',
        'id="start-default-operation"',
        'id="auto-start-operation"',
        'id="replace-skelly-section"',
        'id="forget-skelly"',
        'id="forget-skelly-dialog"',
        'id="software-update-section"',
        'id="check-for-updates"',
        'id="advanced-bluetooth-section"',
        'id="onboarding-dialog"',
        'id="ssh-access-section"',
        'id="controller-power-section"',
        'id="copy-voice-prompt"',
        'id="update-available-badge"',
    ):
        assert element_id in html
    for mode in ("classic", "ai", "manual"):
        assert f'data-start-operation="{mode}"' in html
    assert 'request("/api/operation/start"' in script
    assert 'request("/api/setup/forget-skelly"' in script
    assert 'request("/api/media/refresh"' in script
    assert 'if (selectedMode === "classic") await refreshMediaFromSkelly()' in script
    assert 'request(check ? "/api/update/check" : "/api/update/status"' in script
    assert "Skelly ${skellyVersion} · USA ${body.version}" in script
    assert 'request("/api/onboarding/status")' in script
    assert '"/api/system/service/restart"' in script


def test_classic_and_manual_operator_controls_are_present() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    for element_id in (
        'id="add-media"',
        'id="media-filter"',
        'id="media-editor"',
        'id="manual-camera-enabled"',
        'id="manual-microphone-enabled"',
        'id="manual-visitor-indicator"',
        'id="operator-camera-frame"',
        'id="operator-camera-placeholder"',
        'id="operator-camera-result"',
        'data-light-channel="1"',
        'data-light-channel="0"',
        'id="operator-gestures"',
        'data-operator-gesture="look_up"',
        'data-operator-gesture="yes"',
        'data-operator-gesture="no"',
        'data-operator-gesture="laugh"',
        'id="stop-operator-gesture"',
    ):
        assert element_id in html

    for removed_label in (
        "Pretend the visitor said",
        "Manual eyes",
        "Manual movement",
        'id="brain-response-text"',
        'id="brain-conversation"',
    ):
        assert removed_label not in html

    assert "Disconnect Skelly" in script
    assert 'request("/api/hardware/disconnect"' in script
    assert 'request("/api/hardware/lighting"' in script
    assert 'request("/api/media/edit"' in script
    assert 'request("/api/media/enabled"' in script
    assert 'fetch(`/api/media/upload?' in script
    assert "Operator Mode" in html
    assert "AI Mode — Unmanned" in html
    assert 'request("/api/operator/speak"' in script
    assert 'request("/api/operator/gesture"' in script
    assert 'request("/api/operator/gesture/stop"' in script
    assert 'fetch(`/api/sensors/camera/frame.jpg?' in script
    assert 'body: JSON.stringify({ gesture: "listen" })' in script
    assert html.index('id="operator-gestures"') > html.index('id="hardware-result"')
    assert 'fppOverrideSetting.hidden = !available' in script
    assert 'hardwareProfile.value === "dac" && allowFppOverride.checked' in script
    assert 'document.querySelector("#dac-controller-section")' in script
    diagnostics_layout = script.split("diagnostics: [", 1)[1].split("],", 1)[0]
    setup_layout = script.split("setup: [", 1)[1].split("],", 1)[0]
    assert 'document.querySelector("#software-update-section")' in diagnostics_layout
    assert 'document.querySelector("#software-update-section")' not in setup_layout
    assert 'button.classList.toggle("selected", active)' in script
    assert 'button.setAttribute("aria-pressed", String(active))' in script
    assert 'id="operator-audio-section"' not in html
    assert "Built-in Movement" in html
    assert "Enable movement" in html
    assert "Arm motors" not in html
    assert "Groq Llama" not in html
    assert "Free Testing" not in html
    assert 'id="elevenlabs-agent-id"' not in html


def test_pi_installer_restarts_an_existing_service_after_upgrade() -> None:
    installer = (ROOT / "deploy" / "bootstrap-pi.sh").read_text(encoding="utf-8")

    assert 'pip install --upgrade --no-cache-dir "${PROJECT_DIR}"' in installer
    assert "sudo systemctl restart skelly-ai" in installer


def test_image_enables_required_system_helper_and_radio_support() -> None:
    service = (ROOT / "deploy" / "skelly-ai.service.in").read_text(encoding="utf-8")
    helper = (ROOT / "deploy" / "usa-system-helper.py").read_text(encoding="utf-8")
    image_installer = (
        ROOT / "image" / "pi-gen-stage" / "00-install-skelly-ai" / "files" / "install-chroot.sh"
    ).read_text(encoding="utf-8")

    assert "NoNewPrivileges=false" in service
    assert 'run("rfkill", "unblock", "wifi"' in helper
    assert 'run("rfkill", "unblock", "bluetooth"' in helper
    assert 'run("systemctl", "start", "hciuart.service"' in helper
    for package in ("dnsmasq-base", "firmware-brcm80211", "pi-bluetooth", "rfkill"):
        assert package in image_installer
    assert "hciuart.service" in image_installer
    assert 'SUPPORT_USER = "dadtech"' in helper
    assert 'FIRST_USER_NAME=\'dadtech\'' in (
        ROOT / "image" / "build-image.sh"
    ).read_text(encoding="utf-8")
    assert "wifi-scan.json" in helper
    assert '"first-boot-reset"' in helper
    assert '"SKELLY_ONBOARDING_REQUIRED": "true"' in helper
    assert 'run("hostnamectl", "set-hostname", "usa-controller"' in helper
    assert "address=/#/192.168.4.1" in image_installer
    assert "monitor.bluez = required" in image_installer
    assert "bluez5.roles = [ a2dp_sink a2dp_source ]" in image_installer
    assert "dadtech ALL=(root) NOPASSWD: /usr/local/libexec/usa-system-helper *" in image_installer


def test_live_installer_configures_headless_bluetooth_audio_and_wifi_retries() -> None:
    installer = (ROOT / "deploy" / "bootstrap-pi.sh").read_text(encoding="utf-8")
    helper = (ROOT / "deploy" / "usa-system-helper.py").read_text(encoding="utf-8")
    environment = (ROOT / "deploy" / "skelly-ai.env.example").read_text(
        encoding="utf-8"
    )

    assert "monitor.bluez = required" in installer
    assert "bluez5.roles = [ a2dp_sink a2dp_source ]" in installer
    assert 'systemctl --user restart pipewire.service wireplumber.service' in installer
    assert "def scan_and_cache(device: str, attempts: int = 5)" in helper
    assert "for _ in range(attempts):" in helper
    assert "SKELLY_CLASSIC_AUDIO_NAME=Skelly(Live)" in environment
    assert "SKELLY_CLASSIC_AUDIO_PIN=0727" in environment


def test_setup_keeps_wifi_management_available_after_onboarding() -> None:
    html = (ROOT / "src" / "skelly_ai" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    script = (ROOT / "src" / "skelly_ai" / "static" / "app.js").read_text(
        encoding="utf-8"
    )

    for identifier in (
        'id="wifi-settings-section"',
        'id="setup-wifi-select"',
        'id="setup-wifi-connect"',
        'id="setup-wifi-refresh"',
        'id="setup-wifi-hotspot"',
    ):
        assert identifier in html
    assert 'request("/api/system/wifi/refresh"' in script
    assert 'request("/api/system/wifi/hotspot"' in script
    assert "ssh ${body.username}@${body.hostname}.local" in script
    assert 'hardwareConnection.textContent = body.hardware.connected ? "prop connected" : "prop disconnected"' in script
    assert 'link.href = "http://usa-controller.local/"' in script
