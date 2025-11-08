# app/audio.py
import os
import shutil
from pydub import AudioSegment
from pydub.effects import normalize
from gtts import gTTS
from pathlib import Path

def check_ffmpeg():
    ffmpeg_path = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg not found on PATH. Install ffmpeg.")
    return ffmpeg_path

def synthesize_and_process(sinhala_text: str, out_path: str, lang="si", slow_tts=False, speed_factor=0.92, gain_db=6.0):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp_path = out_path + ".tmp_tts.mp3"
    tts = gTTS(text=sinhala_text, lang=lang, slow=slow_tts)
    tts.save(tmp_path)
    check_ffmpeg()
    audio = AudioSegment.from_file(tmp_path, format="mp3")
    if speed_factor != 1.0:
        new_frame_rate = int(audio.frame_rate * speed_factor)
        audio = audio._spawn(audio.raw_data, overrides={"frame_rate": new_frame_rate})
        audio = audio.set_frame_rate(44100)
    if gain_db is not None and gain_db != 0:
        audio = audio.apply_gain(gain_db)
    audio = normalize(audio)
    audio.export(out_path, format="mp3", bitrate="128k")
    try:
        os.remove(tmp_path)
    except Exception:
        pass
    return out_path
