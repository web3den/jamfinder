# How it works

## The idea

Picture a valley at night. Someone is shouting, and you cannot tell from where. Cars drive
around the valley, and each car reflects a little of the shout towards you.

A sound that bounces off a moving car changes pitch, like a passing siren. How much depends on
how the car moves relative to the shouter and to you. If every car reports where it is and how
fast it moves, the only unknown in each echo's pitch is where the shouter stands. With enough
cars, only one place explains all the echoes.

jamfinder does this with radio. The shouter is a transmitter, the cars are aircraft, and the
pitch is radio frequency. Aircraft report their position and velocity over ADS-B, and public
networks share these reports.

## Why it is hard

An echo off an airliner is 40 to 60 dB weaker than the direct signal, and lies only a few hertz
to about 140 Hz away from it. No single echo can be seen. The method adds up small amounts of
evidence from many aircraft over many minutes.

## The steps

1. **Record a narrow band around the carrier.** A few hundred hertz either side is enough. The
   receiver stays in one place and only listens.
2. **Use the direct signal as the reference** (`jf/iq.py`). Receivers and transmitters drift in
   frequency. The software follows the direct signal and measures everything relative to it.
   The echoes carry the same drift, so it cancels. This is why a cheap receiver and an ordinary
   computer clock are enough.
3. **Turn the recording into a time and frequency picture** (`jf/scatter.py`). Each aircraft's
   echo draws a faint curve in it.
4. **Build aircraft tracks** from the position reports (`jf/tracks.py`).
5. **Search the map** (`jf/field.py`). For each candidate place, predict the curve each
   aircraft's echo would draw if the transmitter stood there, and add up the power along those
   curves. A wrong place collects only noise. The right place collects a little from every
   aircraft, and the sum stands out. The search starts on a 500 m grid out to 30 km from the
   receiver, refines the best places to a few metres, and fits small clock offsets.
6. **Run control searches.** The same search runs again with the aircraft tracks shifted by
   several minutes, and with the frequency axis flipped. No place can be right in these runs, so
   their scores show what chance alone produces on this recording.
7. **Decide whether to report** (`jf/rules.py`). A place is reported only if all four of these
   hold. Otherwise the answer is "nothing".
   - The search with the frequency axis flipped finds nothing.
   - The best score is at least 3 times the highest score of the time-shifted searches.
   - After the echoes explained by the best place are erased, what is left scores below that
     highest score.
   - The second-best place scores less than 0.75 of the best.

## The score

A place's score says how far its collected power stands above noise, in units of the noise's
own spread. Away from the transmitter it is about zero, give or take one. The demo's simple
check answers only above 15. The full analysis compares the best score with the control
searches instead, as in step 7.

## Why one receiver is enough

Most ways to locate a transmitter need several receivers or a special antenna.

| Method | What it needs |
|---|---|
| Direction finding | A directional antenna or an antenna array, at several places or on a vehicle |
| Time difference between receivers | Three or more receivers with clocks matched to tens of billionths of a second |
| Signal strength mapping | A vehicle driving around the area |
| This method | One fixed receiver, one plain antenna, an ordinary internet clock |

Here the aircraft do the moving. Each aircraft, at each moment, is a reflector at a known place
with a known velocity. An hour of traffic gives many measurements from many directions.

Timing matters far less than in the time-difference method. There, a clock error turns into a
position error at the speed of light. Here it only moves an aircraft along its path, at
aircraft speed. A tenth of a second is good enough.

## Two things that follow from the geometry

**The mirror problem.** One aircraft flying straight cannot tell a transmitter from its mirror
image on the other side of its path. Traffic from different directions removes the mirror.
Where nearly all aircraft follow one airway, the mirror stays, and the software reports two
places or none.

**The receiver can locate itself.** The echo frequencies depend on the receiver's position in
the same way as on the transmitter's, so both can be fitted from one recording. The analysis
does this too, because a listed receiver position can be off by hundreds of metres.

## When the direct signal cannot be heard

Sometimes hills or buildings block the direct signal while the aircraft above still see both
ends. Then there is no reference to follow. `jf/blind.py` searches for the place and the
transmitter's slow frequency drift together. It needs stronger echoes than the normal search.

## What it does not use

- No model of how strong each echo should be. Only where each echo should be in frequency.
- No audio. Only the carrier.
- No transmission. It only receives.
- No machine learning. It is a physical model and a search.
