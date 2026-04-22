import pygame


DEFAULT_FREQUENCY = 44100
DEFAULT_SIZE = -16
DEFAULT_OUTPUT_CHANNELS = 2
DEFAULT_BUFFER = 512
DEFAULT_TOTAL_CHANNELS = 8
EXPECTED_MIXER_FORMAT = (
    DEFAULT_FREQUENCY,
    DEFAULT_SIZE,
    DEFAULT_OUTPUT_CHANNELS,
)


def _format_mixer_state(mixer_state):
    if mixer_state is None:
        return "uninitialized"
    frequency, size, channels = mixer_state
    return f"frequency={frequency}, size={size}, channels={channels}"


def init_pygame_audio(total_channels=DEFAULT_TOTAL_CHANNELS):
    pygame.mixer.pre_init(
        DEFAULT_FREQUENCY,
        DEFAULT_SIZE,
        DEFAULT_OUTPUT_CHANNELS,
        DEFAULT_BUFFER,
    )
    if not pygame.get_init():
        pygame.init()
    if not pygame.mixer.get_init():
        pygame.mixer.init(
            frequency=DEFAULT_FREQUENCY,
            size=DEFAULT_SIZE,
            channels=DEFAULT_OUTPUT_CHANNELS,
            buffer=DEFAULT_BUFFER,
        )

    mixer_state = pygame.mixer.get_init()
    if mixer_state != EXPECTED_MIXER_FORMAT:
        raise RuntimeError(
            "pygame.mixer must use the expected audio format "
            f"({_format_mixer_state(EXPECTED_MIXER_FORMAT)}); "
            f"got {_format_mixer_state(mixer_state)}."
        )

    current_channels = pygame.mixer.get_num_channels()
    pygame.mixer.set_num_channels(max(total_channels, current_channels))


class AudioRuntime:
    def __init__(self, total_channels=None):
        if not pygame.mixer.get_init():
            raise RuntimeError("pygame.mixer is not initialized. Call init_pygame_audio() first.")
        required_total_channels = max(
            total_channels or DEFAULT_TOTAL_CHANNELS,
            1,
        )
        pygame.mixer.set_num_channels(required_total_channels)
        pygame.mixer.set_reserved(1)

        self._bgm_channel = pygame.mixer.Channel(0)
        self._bgm_sound = None
        self._bgm_volume = 1.0
        self._bgm_loops = -1

    @property
    def bgm_channel(self):
        return self._bgm_channel

    def play_bgm(self, sound, volume=None, loops=-1):
        self._bgm_sound = sound
        self._bgm_loops = loops
        if volume is not None:
            self._bgm_volume = volume
        self.bgm_channel.play(sound, loops=loops)
        self.bgm_channel.set_volume(self._bgm_volume)

    def restart_bgm(self):
        if self._bgm_sound is not None:
            self.play_bgm(self._bgm_sound, volume=self._bgm_volume, loops=self._bgm_loops)

    def set_bgm_volume(self, volume):
        self._bgm_volume = volume
        self.bgm_channel.set_volume(volume)

    def fadeout_bgm(self, milliseconds):
        self.bgm_channel.fadeout(milliseconds)
