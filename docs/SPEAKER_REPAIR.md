# Repair Skelly Speaker

In **System & Tools → Manage Connections**, refresh speaker status, then choose
**Repair Skelly Speaker**. Read and confirm the speaker-only pairing reset.
Stop active operation first. Keep the intended Skelly powered in Live Mode;
disconnect any phone/computer using its speaker.

The repair scans for Skelly(Live), excludes the configured/current BLE control
addresses, and verifies the speaker identity before removing a bond. It refuses
ambiguous discovery or an unavailable Bluetooth controller. It uses Bluetooth
commands, not deletion of BlueZ database files. Only the identified speaker is
disconnected and forgotten, then rediscovered, paired, trusted and connected.

Success requires a ready PipeWire sink. If Skelly is the selected output, its
sink must also be verified as PipeWire's default output. An existing USB/external
output selection is preserved; the speaker sink is checked without selecting it
as the default. No test speech is played automatically.

Repair work has a 150-second deadline, followed by bounded command cleanup.
It serializes speaker work and rejects conflicting control/audio changes. Existing competing audio-session ownership is released in
cleanup. Failure reports the current problem and allows a deliberate retry.
An old speaker bond cannot be restored after it is forgotten; retry creates a
fresh bond. BLE pairing and unrelated Bluetooth devices are not reset.

The discovery/identity readout describes a known BlueZ record, not proof that a
speaker is currently in range. Live discovery takes place during repair.

## Required hardware verification before publication

Use a spare/test controller; do not run these checks on production implicitly.

- Reproduce a stale Skelly speaker bond after an SD-card swap.
- Record BLE connection/address and unrelated paired devices before/after repair.
- Confirm repair restores pairing, trust, connection and the actual audio sink.
- Check Skelly-selected routing, and preservation of USB/external selection.
- Verify missing/offline speaker, authentication cancellation and missing-sink
  failures do not remove other bonds or claim success.
- Verify timeout/retry and restoration of competing audio-session ownership.
- Check that loss of the speaker replaces stale success text across the UI.
- Run an owner-triggered audio playback test separately.
