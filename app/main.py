import logging
import re
import threading
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from .models import RenderRequest
from .render import render, OUTPUTS
from .media import library
from .tts import VOICES

app = FastAPI(title='Character Reel Renderer')
RENDER_LOCK = threading.Lock()

@app.get('/health')
def health():
    return dict(ok=True, voices_loaded=list(VOICES))

@app.get('/library')
def get_library():
    return library()

@app.post('/render')
def post_render(body: RenderRequest, request: Request):
    if not RENDER_LOCK.acquire(blocking=False):
        raise HTTPException(429, 'Renderer busy; retry later', headers={'Retry-After':'30'})
    try:
        result = render(body)
        for name, output in result['outputs'].items():
            output['url'] = str(request.url_for('output_file', job_id=result['job_id'], filename=name))
        return result
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logging.exception('Render failed')
        raise HTTPException(500, 'Render failed; inspect service logs') from exc
    finally:
        RENDER_LOCK.release()

@app.get('/outputs/{job_id}/{filename}', name='output_file')
def output_file(job_id: str, filename: str):
    if not re.fullmatch(r'[a-f0-9]{32}', job_id) or filename not in ('full.mp4','voice_captions.mp4'):
        raise HTTPException(404)
    path = OUTPUTS / job_id / filename
    if not path.is_file() or not (path.parent/'result.json').is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type='video/mp4', filename=filename)
