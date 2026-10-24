# Camera mounting

Operate → AI mode trigger sources includes **Camera: Stationary / Moves with Skelly**.
The choice saves immediately with the other operation settings. Existing installations
and fresh installations default to Stationary.

Stationary leaves motion triggers unchanged. Moves with Skelly ignores camera motion
as an arrival trigger while USA has commanded prop movement, and for 1.5 seconds
after the stop command. Face/person detection continues. Audio trigger behavior and
visitor departure confirmation are unchanged. Filtered motion must clear before
motion alone can trigger a new arrival; a face arrival can still start a visit.
Continuous background motion must also clear after a confirmed departure.

This uses successful movement commands, not physical position feedback. It cannot
identify movement caused by someone manually moving the prop, and the stock prop
may finish a movement after a stop command. Verify the settling time on the actual
mount. A quick passerby detectable only by motion can be missed during filtering.

Hardware acceptance: select Moves with Skelly, verify unattended animation does not
start repeated visits, approach during a torso turn and confirm face detection,
leave and return to confirm the lure counter resets. Compare Stationary with a
fixed camera. No physical movement test is performed by the automated suite.
