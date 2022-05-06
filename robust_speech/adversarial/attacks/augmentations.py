from torch_audiomentations import Gain, \
                                  AddBackgroundNoise, \
                                  BandPassFilter, \
                                  BandStopFilter, \
                                  AddColoredNoise, \
                                  HighPassFilter, \
                                  LowPassFilter, \
                                  PeakNormalization, \
                                  PitchShift, \
                                  PolarityInversion
#define a series of speech augmentation techniques here

def gain(aug_severity):
    """
    input is the batch original speech signal x_or
    output is the augmented speech signal x_aug
    """
    return Gain(
        min_gain_in_db=-15.0,
        max_gain_in_db=5.0,
        mode='per_example',
        p=1,
    )

# def add_background_noise(aug_severity):
#     """
#     need background noise audio
#     """
#     return AddBackgroundNoise(
#         background_paths=???
#         min_snr_in_db=3.0,
#         max_snr_in_db=30.0,
#         mode="per_example",
#         p=1,
#     )

def band_pass_filter(aug_severity):
    return BandPassFilter(
        min_center_frequency=200,
        max_center_frequency=4000,
        min_bandwidth_fraction=0.5,
        max_bandwidth_fraction=1.99,
        mode="per_example",
        p=1,
    )

def band_stop_filter(aug_severity):
    return BandStopFilter(
        min_center_frequency=200,
        max_center_frequency=4000,
        min_bandwidth_fraction=0.5,
        max_bandwidth_fraction=1.99,
        mode="per_example",
        p=1,
    )

def add_colored_noise(aug_severity):
    return AddColoredNoise(
        min_snr_in_db=3.0,
        max_snr_in_db=30.0,
        min_f_decay=-2.0,
        max_f_decay=2.0,
        mode="per_example",
        p=1,
    )

def high_pass_filter(aug_severity):
    return HighPassFilter(
        min_cutoff_freq=20,
        max_cutoff_freq=2400,
        mode="per_example",
        p=1,
    )

def low_pass_filter(aug_severity):
    return LowPassFilter(
        min_cutoff_freq=150,
        max_cutoff_freq=7500,
        mode="per_example",
        p=1,
    )

def peak_noramalization(aug_severity):
    """
    Apply a constant amount of gain, so that highest signal level present in each audio snippet
    in the batch becomes 0 dBFS, i.e. the loudest level allowed if all samples must be between
    -1 and 1.
    This transform has an alternative mode (apply_to="only_too_loud_sounds") where it only
    applies to audio snippets that have extreme values outside the [-1, 1] range. This is useful
    for avoiding digital clipping in audio that is too loud, while leaving other audio
    untouched.
    """
    return PeakNormalization(
        apply_to="all",
        mode="per_example",
        p=1,
    )

def pitch_shift(aug_severity):
    """
    Pitch-shift sounds up or down without changing the tempo.
    """
    return PitchShift(
        min_transpose_semitones=-4.0,
        max_transpose_semitones=4.0,
        mode="per_example",
        p=1,
        sample_rate=16000
    )

# def polarity_inversion(aug_severity):
#     """
#     Flip the audio samples upside-down, reversing their polarity. In other words, multiply the
#     waveform by -1, so negative values become positive, and vice versa. The result will sound
#     the same compared to the original when played back in isolation. However, when mixed with
#     other audio sources, the result may be different. This waveform inversion technique
#     is sometimes used for audio cancellation or obtaining the difference between two waveforms.
#     However, in the context of audio data augmentation, this transform can be useful when
#     training phase-aware machine learning models.
#     """
#     return PolarityInversion(
#         mode="per_example",
#         p=1,
#     )

augmentations = [
    gain, 
    band_pass_filter, 
    band_stop_filter, 
    add_colored_noise,
    high_pass_filter,
    low_pass_filter,
    peak_noramalization,
    pitch_shift
]