# How it works, in plain language

This page explains the method without the maths. The code is in `jf/`.

## The picture

Stand in a valley at night. Somewhere a person is shouting, and you cannot tell from where.
Cars drive around the valley. Each car reflects a little of the shout towards you.

A sound that bounces off a moving car changes pitch, like a siren passing by. How much the pitch
changes depends on how fast the car moves towards the shouter, and how fast it moves towards you.

Now suppose every car reports its position and speed. You know where you stand. Then the only
thing you do not know about each echo's pitch is where the shouter is. Listen to enough cars,
and only one place explains all the echoes.

Replace the shouter with a radio transmitter, the cars with aircraft, and the pitch with radio
frequency. That is the whole method. Aircraft report position and speed by themselves, through
a public system called ADS-B.

## What makes it hard

The echoes are very weak. An echo off an airliner is ten thousand to a million times weaker
than the direct signal. It sits a few hertz to about 140 hertz away from it. In any one second
of recording an echo is far below the noise. The method never tries to see a single echo. It
adds up tiny amounts of evidence over many aircraft and many minutes.

## The steps

**1. Record a narrow slice of radio around the signal.** The search uses only a few hundred
hertz either side of it. The receiver stands still and only listens.

**2. Use the direct signal as the reference.** Cheap receivers drift in frequency. So do
transmitters. The software follows the direct signal and measures everything relative to it.
Both drifts cancel, because the echoes carry the same drift. This is why a 40 dollar receiver
is good enough, and why no precise clock is needed. Code: `jf/iq.py`.

**3. Turn the recording into a picture.** Time runs one way, frequency offset the other. Each
aircraft's echo is a faint curved line in that picture. Most lines are too faint to see.
Code: `jf/scatter.py`.

**4. Build the aircraft tracks.** The position reports are turned into smooth paths with speed
and direction. Code: `jf/tracks.py`.

**5. Try every place on the map.** For one candidate place, the software predicts the line each
aircraft's echo would draw in the picture if the transmitter stood there. It adds up the power
the recording really has along those lines. A wrong place predicts lines where there is only
noise, and collects nothing. The right place collects a little from every aircraft, and the sum
stands out. Code: `jf/field.py`.

The first pass uses a coarse grid, 500 m apart, out to 30 km from the receiver. The best
places are then refined to a few metres. The software also fits the small time offset between
the recording and the aircraft reports.

**6. Check the answer against tests that cannot be right.** The same search is repeated with
the aircraft tracks shifted by several minutes, and with the frequency axis flipped. No place
can be right in those runs. Whatever score they reach is what chance alone produces on this
recording. A real answer has to stand well above it.

**7. Decide whether to speak.** The software reports one place only if four conditions hold.
Otherwise it says "nothing".

- The test with the frequency axis flipped finds nothing.
- The best score is at least 3 times the highest score of the wrong-track tests.
- After the echo lines that the best place explains are erased, what is left scores below
  that highest wrong-track score.
- The second-best place scores less than 0.75 of the best.

This step is the weakest part of the project. The conditions were rewritten several times on
the same recordings they were judged on. Code: `jf/rules.py`.

## Why one receiver is enough

Most ways to locate a transmitter need several receivers, or a special antenna.

| Method | What it needs |
|---|---|
| Direction finding | A directional antenna or an antenna array, at several places or on a vehicle |
| Time difference between receivers | Three or more receivers with clocks matched to tens of billionths of a second |
| Signal strength mapping | A vehicle driving around the area |
| This method | One fixed receiver, one plain antenna, an ordinary internet clock |

Here the aircraft do the moving. Every aircraft, at every moment, is a reflector at a known
place with a known speed. Twenty aircraft over an hour give many hundreds of measurements from
different directions. The receiver itself can stay where it is.

Timing matters far less than in the time-difference method. There, a clock error turns into a
position error at the speed of light. Here it only moves an aircraft along its own path, at
aircraft speed. A tenth of a second is good enough.

## Two things that follow from the geometry

**The mirror problem.** One aircraft on a straight path cannot tell a transmitter from its
mirror image on the other side of the path. Traffic from different directions removes the
mirror. Where almost all aircraft follow one airway, the mirror stays, and the software
reports two places or none.

**The receiver can find itself.** The echo's frequency depends on the transmitter's place and
on the receiver's place in the same way. So both can be fitted from the same recording. That
matters, because a listed receiver position can be off by hundreds of metres. The analysis
script does this fit by itself.

## A transmitter the receiver cannot hear

Sometimes the receiver hears the echoes and not the direct signal, because a hill or buildings
are in the way while the aircraft above see both ends. Then there is no reference to follow.
The software searches for the place and the slow frequency drift together. On two Helsinki
recordings, with the direct signal removed, this gave 21 m and 27 m. It has less margin: it
failed when the signal was made 15 dB weaker. Code: `jf/blind.py`.

## What the score means

The score of a place is how far its collected echo power stands above what noise would give,
in units of the noise's own spread. Away from the transmitter the score is around zero, give
or take one. The software does not answer below 15. Real finds scored between 100 and 500.
The wrong-track tests on the same recordings scored between 10 and 120.

That last pair of numbers is the honest summary of the project. The right place usually has the
highest score. Whether it is far enough above chance to say so out loud is the hard question.

## What it does not use

- No model of how strong an echo should be. Measured echo strengths were 20 dB or more away
  from the textbook formula, so a model would mislead.
- No voice content. The method uses the carrier only. It does not listen to what is said.
- No transmission of any kind. It only receives.
- No machine learning. It is a physical model and a search.

## Where the idea comes from

The same physics locates emergency beacons from satellites: one moving receiver, a fixed
transmitter, and the Doppler curve of a pass. Here the roles are turned around. The moving
objects are reflectors and the receiver stands still.

The idea of locating a transmitter from aircraft echoes is not ours. Radio-monitoring papers
from China (2009 to 2015) and passive-radar papers (2014 to 2021) describe it, with antenna
arrays and errors of kilometres. A Chinese patent application, CN105717486A, describes a
version with an eight-element antenna array and reports an error under 2 km. It was rejected
in 2019, so it is a public disclosure and not a patent in force, as far as our search could tell.
What this code adds is a working version with one receiver and no antenna array, tried on
real recordings of known transmitters.
