import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app, RENDER_LOCK
from app.captions import pack, write_ass
from app.tts import parse_voice
from app.media import resolve_media, select_music
from app.models import RenderRequest

class ServiceTests(unittest.TestCase):
    def test_phrase_orphan_and_nonoverlap(self):
        words = [dict(text=f'w{i}', start=i*.2, end=i*.2+.25) for i in range(21)]
        phrases = pack(words)
        self.assertTrue(all(2 <= len(p) <= 5 for p in phrases))
        self.assertEqual([w for p in phrases for w in p], words)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'x.ass'
            write_ass(path, words, 5, 'champagne')
            rows = [line.split(',') for line in path.read_text().splitlines() if line.startswith('Dialogue:')]
            self.assertTrue(all(a[2] <= b[1] for a,b in zip(rows, rows[1:])))

    def test_voice_syntax(self):
        self.assertEqual(parse_voice('bf_isabella,bf_alice'), [('bf_isabella',1.),('bf_alice',1.)])
        self.assertEqual(parse_voice('bf_isabella*0.7+bf_alice*0.3')[0][1], .7)
        for bad in ('../secret','bf_emma+af_heart','bf_emma*0','bf_emma,'):
            with self.assertRaises(ValueError): parse_voice(bad)

    def test_local_path_restrictions(self):
        for bad in ('/etc/passwd','relative.mp4','file:///etc/passwd','/workspace/../etc/passwd'):
            with self.assertRaises(ValueError): resolve_media(bad, Path('/tmp/unused'))
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
            link = Path(tmp)/'escape'
            link.symlink_to('/etc/passwd')
            with self.assertRaises(ValueError): resolve_media(str(link), Path('/tmp/unused'))

    def test_api(self):
        client = TestClient(app)
        self.assertEqual(client.get('/health').status_code, 200)
        self.assertEqual(client.get('/library').json()[0]['id'], 'funkorama')
        self.assertEqual(client.get('/outputs/invalid/full.mp4').status_code,404)
        self.assertEqual(client.post('/render',json={'video_url':'x','voiceover':'x','character':{'caption_style':'wrong'}}).status_code,422)
        fake = dict(job_id='a'*32, outputs={'full.mp4':{'path':'/x'},'voice_captions.mp4':{'path':'/y'}})
        with patch('app.main.render', return_value=fake):
            result = client.post('/render',json={'video_url':'/workspace/x','voiceover':'x'})
            self.assertEqual(result.status_code,200)
            self.assertTrue(result.json()['outputs']['full.mp4']['url'].endswith('/full.mp4'))
        RENDER_LOCK.acquire()
        try:
            self.assertEqual(client.post('/render',json={'video_url':'x','voiceover':'x'}).status_code,429)
        finally: RENDER_LOCK.release()

    def test_music_duration(self):
        self.assertEqual(select_music('funky confident', 8)['id'],'funkorama')
        with patch('app.media.library',return_value=[dict(duration_s=1,loop_ok=False)]):
            with self.assertRaises(ValueError): select_music('funk',8)

if __name__ == '__main__': unittest.main()
