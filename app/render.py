import json
import math
import tempfile
import uuid
from fractions import Fraction
from pathlib import Path
import numpy as np
import soundfile as sf
from . import tts
from .captions import words_from_tokens, write_ass
from .media import ROOT, resolve_media, probe, select_music, burn, mux

OUTPUTS = ROOT / 'outputs'

def render(request, out_dir=None):
    tts.parse_voice(request.character.tts_voice_id)
    job_id = uuid.uuid4().hex
    dest = Path(out_dir).resolve() if out_dir else OUTPUTS / job_id
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='input-', dir=dest) as tmp:
        tmp = Path(tmp)
        video = resolve_media(request.video_url, tmp / 'video.download')
        info = probe(video)
        stream = next((s for s in info['streams'] if s['codec_type']=='video'), None)
        if stream is None:
            raise ValueError('Input has no video stream')
        fps = Fraction(stream.get('avg_frame_rate', '24/1'))
        if fps <= 0 or fps > 120:
            raise ValueError('Unsupported frame rate')
        picture = float(stream.get('duration') or info['format']['duration'])
        speed = request.character.tts_speed
        audio, tokens = tts.synthesize(request.voiceover, request.character.tts_voice_id, speed)
        # Include a short audible tail in the freeze budget; never silently truncate speech.
        budget = picture + 2.25
        attempts = []
        while len(audio)/tts.SR + .18 > budget and speed < 1.18:
            attempts.append(speed)
            speed = min(1.18, max(speed + .02, speed * (len(audio)/tts.SR + .18) / budget))
            audio, tokens = tts.synthesize(request.voiceover, request.character.tts_voice_id, speed)
        if len(audio)/tts.SR + .18 > budget:
            raise ValueError('Voiceover exceeds picture + 2.25s even at speed 1.18; shorten the text')
        duration = math.ceil(max(picture, len(audio)/tts.SR + .18) * float(fps)) / float(fps)
        audio = np.pad(audio, (0, max(0, round(duration*tts.SR)-len(audio))))
        sf.write(dest / 'voice.wav', audio, tts.SR, subtype='PCM_24')
        words = words_from_tokens(tokens)
        if not words:
            raise ValueError('Kokoro returned no word timestamps')
        phrases = write_ass(dest/'captions.ass', words, duration, request.character.caption_style, request.character.caption_highlight_color)
        (dest/'timings.json').write_text(json.dumps(dict(words=words, phrases=phrases, duration_s=duration, speed=speed, resynthesis_speeds=attempts), indent=2))
        if request.music_url:
            music_path = resolve_media(request.music_url, tmp/'music.download')
            music = dict(id='custom',title='User supplied',artist=None,license='User supplied; verify rights',attribution=None)
        else:
            music = select_music(request.music_mood, duration)
            music_path = ROOT / 'library' / music['path']
        burn(video, dest/'picture.mp4', dest/'captions.ass', duration, str(fps), picture)
        duration = float(next(s for s in probe(dest/'picture.mp4')['streams'] if s['codec_type']=='video')['duration'])
        mux(dest/'picture.mp4', dest/'voice.wav', dest/'voice_captions.mp4', duration)
        mux(dest/'picture.mp4', dest/'voice.wav', dest/'full.mp4', duration, music_path)
    result = dict(job_id=job_id, duration_s=duration, character=request.character.model_dump(), caption=request.caption,
                  voice=dict(id=request.character.tts_voice_id, language=request.character.tts_voice_id[0], speed=speed),
                  music={k:music.get(k) for k in ('id','title','artist','license','attribution')},
                  outputs={name:dict(path=str(dest/name)) for name in ('full.mp4','voice_captions.mp4')})
    (dest/'result.json').write_text(json.dumps(result, indent=2))
    (dest/'picture.mp4').unlink()
    return result
