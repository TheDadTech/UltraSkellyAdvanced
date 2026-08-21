# Image release gate

Record the tester, date, image filename, checksum, Pi model/RAM, and prop model.
Every required item must pass on a disposable SD card before publication.

## Artifact checks

- [ ] Image filename contains the Skelly AI version.
- [ ] `sha256sum -c IMAGE.sha256` passes.
- [ ] Build-info version and pi-gen commit are present.
- [ ] Source archive contains no `.env`, credentials, saved state, logs, packet
      captures, local model files, virtual environments, or development cards.

## Clean boot without hardware

- [ ] Image boots on a Pi 4 Model B.
- [ ] Customized Wi-Fi, hostname, locale, and password work.
- [ ] SSH is off unless explicitly enabled in Raspberry Pi Imager.
- [ ] Dashboard opens at port 8787 and selects Setup.
- [ ] First-run scan reports no prop without crashing.
- [ ] Motors, DAC transmission, FPP override, and automatic AI mode are off.
- [ ] No Groq or ElevenLabs key is configured.

## Standard hardware

- [ ] BLE scan finds the intended Ultra Skelly or Lethal Lily.
- [ ] Connect, disconnect, forget, and reconnect work.
- [ ] All 18 eye icons, lights, and stock movement groups work.
- [ ] Live Mode, speaker pairing, volume, and first-word protection work.
- [ ] Camera detection, microphone level, and offline transcription work.
- [ ] Classic, Operator, and AI modes stop safely.

## Advanced hardware

- [ ] Advanced profile remains inactive until selected.
- [ ] DAC starts disarmed and jaw defaults to 0.
- [ ] Directional head controls stay within configured travel.
- [ ] FPP override appears only in Advanced and releases control correctly.
- [ ] Loss of ESP32/network does not leave a motor command latched.

## Recovery

- [ ] Wrong Wi-Fi can be corrected by reflashing/customizing the card.
- [ ] Power interruption during ordinary operation recovers to a safe state.
- [ ] Previous known-good image remains downloadable.
- [ ] Release notes identify limitations and support/reporting instructions.
