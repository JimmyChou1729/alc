"""Private JSON-lines worker, executed only by an isolated TTS interpreter."""
from __future__ import annotations

import array
import base64
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import wave


def _load_sherpa(root, kind, model_file):
    import sherpa_onnx

    if kind == "kokoro":
        model = sherpa_onnx.OfflineTtsModelConfig(
            kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                model=str(root / "model.int8.onnx"), voices=str(root / "voices.bin"),
                tokens=str(root / "tokens.txt"), data_dir=str(root / "espeak-ng-data"),
                lexicon=",".join(str(root / p) for p in ("lexicon-us-en.txt", "lexicon-zh.txt")),
            ), num_threads=2, provider="cpu", debug=False,
        )
        rules = ",".join(str(root / p) for p in ("date-zh.fst", "number-zh.fst", "phone-zh.fst"))
    elif kind == "vits":
        model = sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(root / model_file), tokens=str(root / "tokens.txt"),
                data_dir=str(root / "espeak-ng-data"),
            ), num_threads=2, provider="cpu", debug=False,
        )
        rules = ""
    else:
        raise ValueError("Unsupported local speech model")
    config = sherpa_onnx.OfflineTtsConfig(model=model, rule_fsts=rules, max_num_sentences=1)
    if not config.validate():
        raise RuntimeError("Invalid local speech model")
    return sherpa_onnx.OfflineTts(config)


def _load_kitten(root, model_file):
    # Fail before importing the library; a missing local file must never fall back to Hub.
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    if config.get("model_file") != model_file or config.get("voices") != "voices.npz":
        raise ValueError("Unexpected Kitten model configuration")
    if Path(model_file).name != model_file or not all((root / name).is_file() for name in (model_file, "voices.npz")):
        raise ValueError("Incomplete local Kitten model")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1")

    def offline_only(event, _args):
        if event in {"socket.connect", "socket.getaddrinfo"}:
            raise OSError("Local speech runtime has no network access")
    sys.addaudithook(offline_only)
    # The public KittenTTS wrapper always downloads from Hub and prints the input text.
    from kittentts.onnx_model import KittenTTS_1_Onnx
    return KittenTTS_1_Onnx(
        model_path=str(root / model_file), voices_path=str(root / "voices.npz"),
        speed_priors=config.get("speed_priors", {}), voice_aliases=config.get("voice_aliases", {}),
    )


def main() -> None:
    root = Path(sys.argv[1])
    kind = sys.argv[2] if len(sys.argv) > 2 else "kokoro"
    model_file = sys.argv[3] if len(sys.argv) > 3 else "model.int8.onnx"
    with open(os.devnull, "w") as quiet:
        with redirect_stdout(quiet):
            tts = _load_kitten(root, model_file) if kind == "kitten" else _load_sherpa(root, kind, model_file)
        for line in sys.stdin:
            try:
                request = json.loads(line)
                with redirect_stdout(quiet):
                    if kind == "kitten":
                        import numpy as np
                        samples = np.asarray(tts.generate(
                            request["text"], voice=request["voice"], speed=request["rate"], clean_text=True,
                        )).reshape(-1)
                        sample_rate = 24000
                    else:
                        audio = tts.generate(request["text"], sid=request["voice"], speed=request["rate"])
                        samples, sample_rate = audio.samples, audio.sample_rate
                if len(samples) == 0:
                    raise ValueError("Empty audio")
                pcm = array.array("h", (round(max(-1.0, min(1.0, float(x))) * 32767) for x in samples))
                if sys.byteorder != "little":
                    pcm.byteswap()
                buffer = io.BytesIO()
                with wave.open(buffer, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(sample_rate)
                    wav.writeframes(pcm.tobytes())
                result = {"audio": base64.b64encode(buffer.getvalue()).decode("ascii")}
            except Exception:
                result = {"error": "Synthesis failed"}
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
