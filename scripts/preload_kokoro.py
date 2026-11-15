"""Build-time only: populate the Hugging Face cache; never run at startup."""
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="hexgrad/Kokoro-82M",
    allow_patterns=["config.json", "kokoro-v1_0.pth", "voices/*.pt"],
)
