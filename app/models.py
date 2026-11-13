from typing import Literal
from pydantic import BaseModel, Field

class Character(BaseModel):
    id: str = 'aria'
    name: str = 'Aria Cole'
    tts_voice_id: str = 'bf_isabella'
    tts_speed: float = Field(default=1.0, ge=0.5, le=1.18)
    caption_style: Literal['champagne', 'soft_pink'] = 'champagne'
    caption_highlight_color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')

class RenderRequest(BaseModel):
    video_url: str
    voiceover: str = Field(min_length=1, max_length=10000)
    caption: str | None = None
    music_mood: str = 'upbeat funky confident'
    music_url: str | None = None
    character: Character = Field(default_factory=Character)
