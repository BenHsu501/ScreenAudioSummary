import sys
import os
import time
import threading
import subprocess
import signal
from openai import OpenAI
import webrtcvad
from pydub import AudioSegment
from io import BytesIO

class AudioStream:
    def __init__(self):
        self.vad = webrtcvad.Vad()
        self.vad.set_mode(1)  # 模式可以是 0, 1, 2, 3，其中 3 最为严格
        self.client = OpenAI()

    def transcribe_audio(self, audio_file):
        transcription = self.client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file,
            response_format="text"
        )
        return transcription
    
    def process_audio_stream(self):
        command = [
            'ffmpeg',
            '-f', 'avfoundation',  # macOS 设备捕获
            '-i', ':0',            # 默认音频输入设备
            '-acodec', 'pcm_s16le',  # 输出 PCM 16位小端数据
            '-ar', '16000',         # 采样率设置为 16000 Hz
            '-ac', '1',             # 单声道音频
            '-f', 's16le',          # 输出格式为 raw PCM
            'pipe:1'                # 输出到 stdout
        ]

        process = subprocess.Popen(command, stdout=subprocess.PIPE)

        frame_duration = 10  # 每幀 10 ms
        frames_per_check = 50  # 每 50 幀檢查一次，即 500 ms
        frame_width = 2 * 16000 * frame_duration // 1000  # 2 bytes per sample
        check_width = frame_width * frames_per_check

        audio_buffer = AudioSegment.empty()
        silence_duration = 0
        while True:
            data = process.stdout.read(check_width)
            if not data:
                break

            # 分析這 500 ms 的音頻
            speech_frames = 0
            for i in range(frames_per_check):
                frame = data[i*frame_width:(i+1)*frame_width]
                if self.vad.is_speech(frame, 16000):
                    speech_frames += 1
            is_speech = speech_frames > frames_per_check // 2  # 如果超過一半的幀是語音，就認為這 500 ms 是語音 

            if is_speech and len(audio_buffer) < frames_per_check*10*15:
                #print("Speech detected")
                audio_segment = AudioSegment(data, sample_width=2, frame_rate=16000, channels=1)
                audio_buffer += audio_segment
                silence_duration = 0
                #print(1, len(audio_buffer))
            else:
                #print("No speech detected")
                silence_duration += frame_duration * frames_per_check

                # 如果静音持续超过 2 秒，且缓冲区中有数据，则进行处理
                if silence_duration > 2000 and len(audio_buffer) > 0:
                    audio_data = audio_buffer.export(format="mp3")
                    audio_file = BytesIO(audio_data.read())
                    audio_file.name = "audio.mp3"  # OpenAI API 需要文件名
                    result = self.transcribe_audio(audio_file)
                    print("Transcription:", result)
                    audio_buffer = AudioSegment.empty()  # 清空缓存
                    silence_duration = 0

        # 确保处理完所有数据
        if len(audio_buffer) > 0:
            audio_data = audio_buffer.export(format="mp3")
            audio_file = BytesIO(audio_data.read())
            audio_file.name = "audio.mp3"
            result = self.transcribe_audio(audio_file)
            print("Final transcription:", result)

        process.wait()

if __name__ == "__main__":
    client = AudioStream()
    client.process_audio_stream()