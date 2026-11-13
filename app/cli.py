import argparse
import json
from .models import RenderRequest, Character
from .render import render

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--video', required=True)
    p.add_argument('--voiceover', required=True)
    p.add_argument('--style', choices=['champagne','soft_pink'], default='champagne')
    p.add_argument('--voice', default='bf_isabella')
    p.add_argument('--speed', type=float, default=1.)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--music-url')
    p.add_argument('--music-mood', default='upbeat funky confident')
    a = p.parse_args()
    request = RenderRequest(video_url=a.video, voiceover=a.voiceover, music_url=a.music_url, music_mood=a.music_mood,
                            character=Character(tts_voice_id=a.voice, tts_speed=a.speed, caption_style=a.style))
    print(json.dumps(render(request, a.out_dir), indent=2))

if __name__ == '__main__':
    main()
