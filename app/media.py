import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]

def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise RuntimeError(result.stderr[-6000:])
    return result.stdout + result.stderr

def probe(path):
    return json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))

def resolve_media(value, temp):
    if value.startswith(('http://', 'https://')):
        with httpx.stream('GET', value, follow_redirects=True, timeout=90) as response:
            response.raise_for_status()
            size = 0
            with temp.open('wb') as output:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 1024**3:
                        raise ValueError('Download exceeds 1 GiB')
                    output.write(chunk)
        return temp
    path = Path(value)
    if not path.is_absolute():
        raise ValueError('Media path must be absolute')
    path = path.resolve()
    if not any(path.is_relative_to(root) for root in (Path('/workspace'), Path('/data'))):
        raise ValueError('Local media must be under /workspace or /data')
    if not path.is_file():
        raise ValueError('Media file does not exist')
    return path

def library():
    return json.loads((ROOT / 'library/tracks.json').read_text())

def select_music(mood, duration):
    import re
    query = set(re.findall(r'\w+', mood.lower()))
    candidates = [t for t in library() if t['duration_s'] >= duration or t['loop_ok']]
    if not candidates:
        raise ValueError('No music track fits the clip')
    return max(candidates, key=lambda t: (3*len(query & set(t['moods'])) + 2*len(query & set(t['tags'])) + 2*int(t['instrumental']), t['id']))

def burn(src, dest, ass, duration, fps, src_duration):
    # All filter paths are service-generated, never user text.
    vf = f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},tpad=stop_mode=clone:stop_duration={max(0,duration-src_duration)+1},ass=filename='{ass}':fontsdir='{ROOT / 'fonts'}'"
    log = run(['ffmpeg','-y','-threads','2','-i',str(src),'-vf',vf,'-t',str(duration),'-an','-c:v','libx264','-threads','2','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(dest)])
    (dest.parent / 'ffmpeg-font.log').write_text(log)

def mux(video, wav, dest, duration, music=None):
    voice = f'[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,apad=whole_dur={duration},atrim=0:{duration},asetpts=PTS-STARTPTS'
    inputs = ['-i',str(video),'-i',str(wav)]
    if music:
        inputs += ['-stream_loop','-1','-i',str(music)]
        fc = voice + '[voice];' + f'[2:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,atrim=0:{duration},asetpts=PTS-STARTPTS,afade=t=in:d=0.25,afade=t=out:st={max(0,duration-.55)}:d=0.5,volume=0.20[mus];[voice]asplit[v][sc];[mus][sc]sidechaincompress=threshold=0.04:ratio=8:attack=15:release=220:makeup=1.1:knee=6[ducked];[v][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]'
    else:
        fc = voice + '[a]'
    run(['ffmpeg','-y',*inputs,'-filter_complex',fc,'-map','0:v:0','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart',str(dest)])
