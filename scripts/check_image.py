"""CPU-only speech check, also run by CI with the container network disabled."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import torch
from app.tts import synthesize

assert torch.version.cuda is None, "Expected CPU-only torch"
assert Path("fonts/Poppins-ExtraBold.ttf").stat().st_size > 0
subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.DEVNULL)
subprocess.run(["ffprobe", "-version"], check=True, stdout=subprocess.DEVNULL)
for voice in ("bf_isabella", "bf_isabella*0.7+bf_alice*0.3", "af_heart"):
    audio, tokens = synthesize("The studio is ready for a sound check.", voice, 0.90)
    assert audio.size > 0 and tokens, f"Missing speech or timestamps: {voice}"
print("Offline CPU image check passed")
