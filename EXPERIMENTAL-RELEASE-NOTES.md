# UltraSkellyAdvanced 0.30.1-beta1

**Experimental Raspberry Pi 3B support. Hardware validation is pending.**

This separate beta retains the existing Raspberry Pi 4 and Pi 5 boot paths. It
does not establish tested compatibility on those boards or on the Pi 3B. The
stable 0.30.0 image and update feeds are unchanged.

- More reliable hotspot startup: bounded retries, independent Bluetooth startup,
  and automatic recovery after a failed home Wi-Fi connection.
- The setup hotspot stays available alongside Ethernet while hotspot mode is
  selected. Healthy hotspots and working home connections are left alone.
- WPS is explicitly disabled on the setup profile; connect using its password.
- A low-priority Ethernet profile requests an address automatically from a router
  with DHCP. Existing owner profiles take priority.
- A lightweight monitor/keyboard screen lets you select home Wi-Fi and enter its
  password without a desktop, browser, Linux login, or SSH. Once connected, it
  displays the real dashboard address and `http://usa-controller.local`.
- Local Qwen is not loaded automatically on Pi 3B or Pi 3B+, preserving their
  limited RAM for setup and controller operation. Model files remain on the card.
- Automatic, bounded support snapshots and persistent logs help diagnose failures.
  A report is exported to the SD card's Windows-readable boot partition.

## End-user test

1. Save any data on your existing card. Flash this beta to a **spare** card using
   Raspberry Pi Imager's custom-image option. For the first baseline test, skip
   Imager account/Wi-Fi customizations and use USA's setup screen/hotspot.
2. Boot the Pi and allow 5-10 minutes for initial setup and card expansion. Keep
   it powered while this runs. The monitor should show network setup without a
   Linux login. A keyboard is optional unless selecting Wi-Fi on the monitor.
3. Connect Ethernet to your **router**, or select home Wi-Fi with the keyboard.
   Alternatively, join `UltraSkellyAdvanced-Setup` with password `dadtech1` from
   your phone and open `http://192.168.4.1`. Remain connected if it says no internet.
4. Once on your home network, use the monitor's IP address or
   `http://usa-controller.local` to finish prop pairing/configuration.
5. Test one restart. During initial hotspot setup, test Ethernet connected before
   boot, then inserted/removed after boot. The hotspot should remain available.
   A valid home Wi-Fi selection intentionally takes the single radio out of AP mode.
6. If it fails, record the board model, what you tried, approximate timing, and
   the exact monitor/phone message. Shut down through the dashboard if available;
   avoid repeated power cuts. After power-off, read the card in your computer and
   send `USA-BETA-DIAGNOSTICS.txt` from the `bootfs` partition. It should appear
   after roughly the first minute. **Do not reflash before saving it.**

Reports include network names, local addresses and service errors. They do not
intentionally collect passwords, keys, credential files or Bluetooth bonds.
Review reports before sharing. If no report exists, report that fact too.

## Limits and recovery

- Software tests and filesystem verification cannot replace a real hardware test.
- Pi 3B/3B+ full local conversational AI plus camera/Vosk workloads are not a
  validated 1 GB configuration. Test control/audio first, then add workloads.
- Monitor Wi-Fi setup targets ordinary password-protected home networks;
  enterprise/captive-portal Wi-Fi may need separate configuration.
- Wi-Fi scan refresh briefly pauses the single-radio setup hotspot; restoration
  is attempted immediately and the recovery timer provides another retry.
- Existing Linux support accounts remain locked until enabled with a unique
  password through the dashboard. No public Linux recovery password is added.
- The console permits first-boot networking only. After USA onboarding completes,
  use the dashboard for changes. It does not expose a shell or power controls.
- Preserve diagnostic reports before returning to your known-good stable card.
  Keep application settings/media backups separately; this beta is a fresh image.

## Build provenance

This candidate is an offline overlay on the byte-verified clean published 0.30.0
image. Its original kernel, firmware, OS packages and partition layout are retained;
no desktop/browser packages were added and no ARM executables ran on the build
host. The source snapshot, overlay manifest, filesystem reports and image checksum
are delivered with it. The build script can replay the overlay from that base.
This is not a new pi-gen/apt rebuild and is not claimed to be bit-reproducible.
