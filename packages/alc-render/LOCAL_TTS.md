# Optional local speech

System speech remains available without installing models. Local speech is an
optional CPU-based providers running outside the browser: Kokoro, Piper and
KittenTTS. No model is downloaded by opening a Reader or checking status.

## Install and try

In LocalWeb, open **Settings → TTS 朗读引擎**. Choose a model, review its download
and license, and confirm installation. Chinese and English have independent voice
selectors and previews; each local preview player appears below its own button,
above Save. Preview uses current selections immediately. Save sets the default
voice for each language; the languages can use different installed models, or
system speech. Installation alone does not change the selected voice.

The first supported model is `kokoro-int8-multi-lang-v1_1`: its download is
147,031,220 bytes (about 140 MiB), with additional runtime downloads and unpacked
files. The model is Apache-2.0; retain the bundled dependency notices as well.
The runtime is installed into its own virtual environment; it does not replace
system Python packages. A compatible Python 3.11+ interpreter and platform wheels
for sherpa-onnx 1.12.29 and NumPy 2.2.6 are required. Installation failures are
reported and can be retried; a checksum-verified model archive is reused.

An Agent installation can use the existing `alc-render` command without installing
LocalWeb:

```sh
alc-render tts status
alc-render tts install --yes
alc-render tts configure --enable
alc-render tts voices
alc-render tts speak --text "这是一次本地朗读试听。" --output sample.wav
alc-render tts open document.html
```

`install --yes` is explicit download consent. Installation alone does not enable
local speech. `open` accepts an ALC standalone Reader HTML, opens the default
browser, and keeps its local service running until Ctrl+C. It never rewrites the
HTML. CLI Readers keep a per-document port mapping in the local TTS directory
so reopening the same document can reuse its browser preferences and directory
association. `speak` refuses to overwrite an existing output file.

Use `alc-render tts configure --disable` to return to system speech. The default
local configuration and model directory is `~/.alc/tts`; `ALC_TTS_DIR` overrides
it. LocalWeb and Agent commands must use the same directory to share installation
and voice settings. Downloaded files remain local when speech is disabled.

## Reading and portability

The Reader has one voice selector per language. Installed model voices appear
first, grouped by model, followed by browser/system voices. The selected voice
determines the engine; there is no separate engine switch. Model availability is
refreshed when reopening the speech panel, without regenerating the document.
Existing Kokoro settings are mapped to the corresponding voice selections.
A Reader opened
through LocalWeb or `tts open` receives a connection to the local audio service.
The existing speech buttons, segment highlighting, previous/next, looping and
pause/resume controls continue to work. Local speech prepares a complete paragraph
before starting it. Oversized paragraphs are split at natural boundaries near a
safe request limit (400 code points for Chinese, 1600 for English), rather than
at every sentence. A serial background queue targets 45 seconds of upcoming
playback, capped at three chunks and 32 MiB. A separate 32 MiB in-memory LRU
retains generated audio across stops and replays. A slow model can still exhaust
the buffer; buffering improves continuity but does not increase inference speed.

Local audio is synthesized at 1× and playback speed is applied in the browser with
pitch preservation. Changing speed retains the current playback position and
reuses generated audio. Faster playback consumes buffered audio more quickly.
System voices continue to use the browser's speech-synthesis rate controls.
Chinese and English use their selected voices. Unsupported languages and service
failures display an error so the user can choose another available voice; they do
not silently substitute another engine. Mathematical notation and specialist
pronunciations still depend on the Reader's text preparation and selected model.

A downloaded HTML does not include the local connection capability, model weights
or cached audio. Double-clicking it retains system speech; reopen it through the
local launcher for enhanced speech. Audio synthesis is serial, with a bounded
in-memory cache; stopping or switching segments aborts pending requests and their
synthesis when the Reader connection closes. Text and generated
audio are not written to synthesis logs or persistent caches. Explicit WAV exports
are written only to the requested output path.

## Available models

Alongside Kokoro, two optional sherpa-onnx Piper packages are available in Settings: `vits-piper-zh_CN-huayan-medium` (Chinese) and
`vits-piper-en_US-lessac-medium` (English), each about 67 MB before unpacking.
They require separate, explicit installation. Huayan's model card lists the
dataset license as **Unknown**; Lessac links to the Blizzard 2013 dataset license.
Review the displayed license information and the model cards before downloading
or using these voices.
Smaller downloads do not establish better pronunciation or faster generation;
preview on the target machine before choosing a voice for reading.

### KittenTTS English voices

The model catalog also includes KittenTTS Micro 0.8 (40M parameters) and
Mini 0.8 (80M parameters), with eight named English voices: Bella, Jasper, Luna,
Bruno, Rosie, Hugo, Kiki and Leo. Use the English voice selector to audition
them. Each model is installed only after confirmation, and preview does not change
the Reader's saved voice. The model cards list Apache-2.0 licensing.

KittenTTS uses a separate runtime from Kokoro/Piper. Its installation includes
runtime dependencies (including ONNX Runtime, spaCy and phonemization libraries)
in addition to the model download shown in the page; the displayed model size is
not the total installation size. Micro and Mini share this separate runtime.
Models load from the verified local files; missing files require installation
rather than triggering a download during preview. The smallest Nano INT8 variant is not included because the official project currently
notes reported issues with that variant. Actual pronunciation and performance
must be compared locally; parameter count alone does not determine either.

Sources: [KittenTTS project](https://github.com/KittenML/KittenTTS),
[Micro model](https://huggingface.co/KittenML/kitten-tts-micro-0.8),
[Mini model](https://huggingface.co/KittenML/kitten-tts-mini-0.8).

## Connection boundary

The Reader service binds only to IPv4 loopback and uses an unpredictable,
per-document URL. Its audio routes support status and synthesis only; they cannot
install a model, change configuration, access arbitrary files or manage Web jobs.
Synthesis requires a matching Origin and bounded JSON request. The Reader's CSP
permits connections only to its own audio path and playback of in-memory audio.
LocalWeb installation/configuration routes retain the application's authentication
and same-origin checks. Local model inference does not send document text to a
remote speech service.

## Development verification

Closing a Web preview cancels its queued or active synthesis without cancelling
other Readers.

An internal comparison tool remains available at `/?view=tts-lab`, without an
entry in user Settings. It generates the same text sequentially for two choices
and shows separate audio players, synthesis time and audio duration. Preview
bypasses the audio cache; resident models can still be warm. Timings can include
waiting for other requests and are not Reader first-audio latency measurements.

Tests use fake models and workers by default. Real model installation, performance,
pronunciation and audio quality require an explicit download and listening test on
the target machine. Keep those checks separate from offline package tests.

Official sources:
- [Kokoro model card](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh)
- [sherpa-onnx model packages](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kokoro.html)
