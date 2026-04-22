import array
import math
import re
from collections.abc import Iterable
from enum import Enum
from functools import lru_cache
from typing import cast

import pygame

from audio_runtime import EXPECTED_MIXER_FORMAT


SAMPLE_RATE = 44100
_NOTE_PATTERN = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)$")
_SEMITONES = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}


def _clamp_sample(value):
    return max(-32767, min(32767, int(value)))


# Built-in attenuation for the square component. A unit-amplitude square wave
# is perceived ~10-12 dB louder than a unit sine (rich odd harmonics), so we
# bake in a loudness-compensation gain. With this, ``SQUARE`` matches the
# historical ``wave="square"`` preset exactly.
_SQUARE_GAIN = 0.4

# ---- Named timbres -----------------------------------------------------------
# A *timbre* is a 3-component mix vector ``(sine, triangle, square)`` that says
# how loud each oscillator is in the final tone -- think of it as the synth
# equivalent of an RGB color. Game code is encouraged to use the named
# presets instead of building tuples inline:
#
#     from audio_utils import Timbre
#     generate_samples(440, 0.2, timbre=Timbre.Soft)
#
# Gains are NOT auto-normalized: stacking components past 1.0 may clip, which
# is intentional so kids can hear additive synthesis at work. Keep the sum
# near 1.0 (or lower ``volume``) to stay headroom-safe.

class Timbre(Enum):
    """Built-in named timbre presets.

    Enum gives us a dedicated namespace (``Timbre.Soft``) without taking away
    the flexibility to pass a custom 3-component mix tuple when needed.
    """

    # Three pure oscillators
    Sine = (1.0, 0.0, 0.0)      # smooth, flute-like
    Triangle = (0.0, 1.0, 0.0)  # mellow, slightly buzzy
    Square = (0.0, 0.0, 1.0)    # hollow, retro game console

    # A few hand-tuned mixes worth experimenting with
    Soft = (0.7, 0.3, 0.0)      # warm sine + a touch of triangle
    Hollow = (0.6, 0.0, 0.4)    # sine + square -> clarinet-ish
    Retro = (0.0, 0.5, 0.5)     # triangle + square -> classic 8-bit lead


TimbreInput = Timbre | Iterable[float]

# Named-lookup tables (e.g. for "play every preset" demos).
TIMBRE_PRESETS = {preset.name.lower(): preset for preset in Timbre}
_TIMBRE_IMPORT_HINT = "/".join(f"Timbre.{preset.name}" for preset in Timbre)


def _coerce_timbre(timbre: TimbreInput) -> tuple[float, float, float]:
    """Validate *timbre* and return it as a ``(sine, triangle, square)`` tuple.

    Strings are intentionally NOT accepted -- pass a preset from :class:`Timbre`
    or a 3-element numeric iterable.
    """
    if isinstance(timbre, Timbre):
        return timbre.value
    if isinstance(timbre, str):
        raise TypeError(
            f"timbre must be a 3-component (sine, triangle, square) vector, "
            f"not the string {timbre!r}. Import a preset such as "
            f"{_TIMBRE_IMPORT_HINT} from audio_utils, or "
            f"pass your own tuple like (0.7, 0.3, 0.0)."
        )
    mix = tuple(float(component) for component in timbre)
    if len(mix) != 3:
        raise ValueError(
            f"timbre must have exactly 3 components (sine, triangle, square); got {mix!r}."
        )
    return mix


def _wave_value(freq, time_s, wave_mix):
    sine_gain, triangle_gain, square_gain = wave_mix
    value = 0.0
    if sine_gain or square_gain:
        sine = math.sin(2 * math.pi * freq * time_s)
        if sine_gain:
            value += sine_gain * sine
        if square_gain:
            value += square_gain * _SQUARE_GAIN * (1.0 if sine >= 0 else -1.0)
    if triangle_gain:
        cycle = time_s * freq
        value += triangle_gain * (2 * abs(2 * (cycle - math.floor(cycle + 0.5))) - 1)
    return value


@lru_cache(maxsize=None)
def note_to_freq(note_name):
    if note_name in (None, "R", "REST"):
        return 0.0

    match = _NOTE_PATTERN.match(str(note_name))
    if not match:
        raise ValueError(f"Unsupported note format: {note_name}")

    note = match.group(1).upper() + match.group(2)
    octave = int(match.group(3))
    midi = (octave + 1) * 12 + _SEMITONES[note]
    return 440.0 * (2 ** ((midi - 69) / 12))


def generate_samples(
    freq,
    duration,
    volume=0.25,
    timbre: TimbreInput = Timbre.Sine,
    fade_out=True,
    fade_in=0.0,
    fade_out_start=0.5,
    release_end=0.0,
    sample_rate=SAMPLE_RATE,
    harmonics=None,
    freq_scale=1.0,
):
    sample_count = max(0, int(sample_rate * duration))
    if sample_count <= 0:
        return []

    if freq <= 0:
        return [0] * sample_count

    harmonic_layers = harmonics or ((1.0, 1.0),)
    wave_mix = _coerce_timbre(timbre)
    fade_in_samples = int(sample_rate * fade_in) if fade_in > 0 else 0
    fade_out_index = int(sample_count * fade_out_start)
    out = []

    for index in range(sample_count):
        t = index / sample_rate
        value = 0.0
        for multiplier, gain in harmonic_layers:
            value += gain * _wave_value(freq * freq_scale * multiplier, t, wave_mix)

        envelope = 1.0
        if fade_in_samples > 0 and index < fade_in_samples:
            envelope *= index / max(1, fade_in_samples)

        if fade_out and index > fade_out_index:
            fade_span = max(1, sample_count - fade_out_index)
            progress = (index - fade_out_index) / fade_span
            envelope *= 1.0 - progress * (1.0 - release_end)

        out.append(_clamp_sample(value * envelope * volume * 32767))

    return out


def generate_sweep_samples(
    start_freq,
    end_freq,
    duration,
    volume=0.25,
    timbre: TimbreInput = Timbre.Sine,
    sample_rate=SAMPLE_RATE,
    decay_power=1.0,
):
    sample_count = max(0, int(sample_rate * duration))
    if sample_count <= 0:
        return []

    wave_mix = _coerce_timbre(timbre)
    out = []
    last_index = max(1, sample_count - 1)
    for index in range(sample_count):
        progress = index / last_index
        t = index / sample_rate
        freq = start_freq + (end_freq - start_freq) * progress
        envelope = 1.0 - (progress ** decay_power)
        value = _wave_value(freq, t, wave_mix) * envelope * volume
        out.append(_clamp_sample(value * 32767))

    return out


def concat_samples(*segments):
    merged = []
    for segment in segments:
        merged.extend(segment)
    return merged


def mix_samples(*tracks):
    max_len = max((len(track) for track in tracks), default=0)
    mixed = []
    for index in range(max_len):
        total = 0
        for track in tracks:
            if index < len(track):
                total += track[index]
        mixed.append(_clamp_sample(total))
    return mixed


def _require_expected_mixer_format():
    mixer_state = pygame.mixer.get_init()
    if mixer_state is None:
        raise RuntimeError("pygame.mixer is not initialized. Call init_pygame_audio() first.")
    if mixer_state != EXPECTED_MIXER_FORMAT:
        frequency, size, channels = mixer_state
        raise RuntimeError(
            "Synthesized sounds require mixer format "
            f"{EXPECTED_MIXER_FORMAT}, got "
            f"(frequency={frequency}, size={size}, channels={channels})."
        )


def make_sound(samples):
    _require_expected_mixer_format()
    mono = array.array("h", samples)
    stereo = array.array("h", [0]) * (len(mono) * 2)
    stereo[0::2] = mono
    stereo[1::2] = mono
    return pygame.mixer.Sound(buffer=stereo)


def synthesize_sound(freq, duration, **sample_kwargs):
    return make_sound(generate_samples(freq, duration, **sample_kwargs))


def notes_to_samples(sequence, beat_duration, note_map=None, sample_rate=SAMPLE_RATE, **sample_kwargs):
    rendered = []
    for entry in sequence:
        if isinstance(entry, tuple):
            note_name, beats = entry
        else:
            note_name, beats = entry, 1

        duration = beats * beat_duration
        if note_map is not None and note_name in note_map:
            freq = note_map[note_name]
        else:
            freq = note_to_freq(note_name)

        rendered.extend(
            generate_samples(freq, duration, sample_rate=sample_rate, **sample_kwargs)
        )
    return rendered
