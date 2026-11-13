import os
import re
import threading
import numpy as np

SR = 24000
LOCK = threading.RLock()
PIPELINES = {}
VOICES = {}

def parse_voice(spec):
    if ',' in spec:
        entries = [(s.strip(), 1.) for s in spec.split(',')]
    else:
        entries = []
        for part in spec.split('+'):
            match = re.fullmatch(r'([a-z]{2}_[a-z0-9]+)(?:\*([0-9]*\.?[0-9]+))?', part.strip())
            if not match:
                raise ValueError('Invalid voice expression')
            entries.append((match[1], float(match[2] or 1)))
    if not entries or any(not re.fullmatch(r'[abefhijpz][fm]_[a-z0-9]+', n) or w <= 0 for n,w in entries):
        raise ValueError('Invalid voice name or weight')
    if len({n[0] for n,w in entries}) != 1:
        raise ValueError('Blended voices must use the same language')
    return entries

def pipeline(lang):
    if lang not in PIPELINES:
        import espeakng_loader
        espeakng_loader.make_library_available()
        os.environ['PHONEMIZER_ESPEAK_LIBRARY'] = espeakng_loader.get_library_path()
        os.environ['ESPEAK_DATA_PATH'] = espeakng_loader.get_data_path()
        from phonemizer.backend.espeak.wrapper import EspeakWrapper
        EspeakWrapper.set_library(espeakng_loader.get_library_path())
        from kokoro import KPipeline
        import torch
        torch.set_num_threads(int(os.environ.get('TTS_THREADS', '4')))
        PIPELINES[lang] = KPipeline(lang_code=lang, repo_id='hexgrad/Kokoro-82M', device='cpu')
    return PIPELINES[lang]

def synthesize(text, spec, speed):
    entries = parse_voice(spec)
    with LOCK:
        pipe = pipeline(entries[0][0][0])
        if spec not in VOICES:
            total = sum(w for _,w in entries)
            VOICES[spec] = sum(pipe.load_voice(n) * (w / total) for n,w in entries)
        parts, tokens, offset = [], [], 0.
        for result in pipe(text, voice=VOICES[spec], speed=speed, split_pattern=r'\n+'):
            if result.audio is None:
                continue
            audio = result.audio.cpu().numpy().reshape(-1)
            parts.append(audio)
            for t in result.tokens or []:
                if t.start_ts is not None and t.end_ts is not None:
                    tokens.append(dict(text=t.text, start=float(t.start_ts)+offset, end=float(t.end_ts)+offset))
            offset += len(audio) / SR
        if not parts:
            raise ValueError('No speech generated')
        audio = np.concatenate(parts)
        peak = np.max(np.abs(audio))
        if peak:
            audio *= .95 / peak
        return audio, tokens
