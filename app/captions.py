import re
from pathlib import Path

def words_from_tokens(tokens):
    words = []
    for token in tokens:
        text = token['text'].strip()
        if not text:
            continue
        if not any(c.isalnum() for c in text):
            if words:
                words[-1]['text'] += text
            continue
        if token['end'] > token['start']:
            words.append(dict(text=text, start=token['start'], end=token['end']))
    return words

def pack(words):
    phrases, current = [], []
    for word in words:
        current.append(word)
        if len(current) == 5 or word['text'].endswith(('.', '?', '!')):
            phrases.append(current)
            current = []
    if current:
        phrases.append(current)
    if len(phrases) > 1 and len(phrases[-1]) == 1:
        previous = phrases[-2]
        take = min(2, len(previous) - 2)
        if take > 0:
            phrases[-1] = previous[-take:] + phrases[-1]
            del previous[-take:]
        elif len(previous) + 1 <= 5:
            previous.extend(phrases.pop())
    return phrases

def ticks(t):
    return max(0, round(t * 100))

def stamp(t):
    h, rest = divmod(t, 360000)
    m, rest = divmod(rest, 6000)
    s, cs = divmod(rest, 100)
    return f'{h}:{m:02}:{s:02}.{cs:02}'

def escape(text):
    return text.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\n', ' ')

def write_ass(path: Path, words, duration, style, override=None):
    color = override or ('#E8C9A1' if style == 'champagne' else '#F3B5C8')
    rgb = color.lstrip('#')
    highlight = f'&H00{rgb[4:6]}{rgb[2:4]}{rgb[:2]}&'
    header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Phrase,Poppins ExtraBold,74,&H00FFFFFF&,&H00FFFFFF&,&HAA000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,5,2,2,90,90,450,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    phrases = pack(words)
    events = []
    for pi, phrase in enumerate(phrases):
        next_start = phrases[pi+1][0]['start'] if pi+1 < len(phrases) else duration
        phrase_end = min(phrase[-1]['end'] + .08, next_start, duration)
        for i, word in enumerate(phrase):
            start = ticks(word['start'])
            end = ticks(phrase[i+1]['start'] if i+1 < len(phrase) else phrase_end)
            if end <= start:
                continue
            parts = []
            for j, w in enumerate(phrase):
                text = escape(w['text'])
                if i == j:
                    text = r'{\c' + highlight + r'\fs82\fscx100\fscy100\t(0,65,\fscx103\fscy103)\t(65,140,\fscx100\fscy100)}' + text + r'{\rPhrase}'
                parts.append(text)
            events.append(f'Dialogue: 0,{stamp(start)},{stamp(end)},Phrase,,0,0,0,,{{\\an2}}' + ' '.join(parts))
    path.write_text(header + '\n'.join(events) + '\n')
    return phrases
