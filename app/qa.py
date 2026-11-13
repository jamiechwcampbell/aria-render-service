"""Extract every mid-word and frames on both sides of phrase boundaries."""
import json
import shutil
from pathlib import Path
from .media import probe, run

def main():
    root = Path(__file__).resolve().parents[1] / 'style-variants'
    summary = []
    for style in ('champagne','soft_pink'):
        folder = root/style
        timings = json.loads((folder/'timings.json').read_text())
        frames = root/'frames'/style
        frames.mkdir(parents=True,exist_ok=True)
        manifest = []
        for i,w in enumerate(timings['words']):
            manifest.append(dict(label=f'word_{i:02}',text=w['text'],time=(w['start']+w['end'])/2))
        for i,p in enumerate(timings['phrases'][1:]):
            for offset,label in ((-1/24,'before'),(0,'boundary'),(1/24,'after')):
                manifest.append(dict(label=f'phrase_{i+1:02}_{label}',time=max(0,p[0]['start']+offset)))
        for item in manifest:
            dest = frames / f"{item['label']}_{item['time']:.3f}.jpg"
            run(['ffmpeg','-y','-v','error','-i',str(folder/'full.mp4'),'-ss',str(item['time']),'-frames:v','1','-q:v','2',str(dest)])
            item['path'] = str(dest)
        (frames/'manifest.json').write_text(json.dumps(manifest,indent=2))
        for name in ('full','voice_captions'):
            target = root/f's04_{style}_{name}.mp4'
            shutil.copy2(folder/f'{name}.mp4',target)
            info = probe(target)
            streams = {s['codec_type']:s for s in info['streams']}
            assert streams['video']['width']==1080 and streams['video']['height']==1920
            assert abs(float(streams['video']['duration'])-float(streams['audio']['duration'])) < 1/24
            summary.append(dict(path=str(target),duration_s=float(streams['video']['duration']),frames=streams['video'].get('nb_frames'),audio_duration_s=float(streams['audio']['duration'])))
    (root/'qa-summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))

if __name__ == '__main__': main()
