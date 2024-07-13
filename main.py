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
    def __init__(self, ):
        self.vad = webrtcvad.Vad()
        self.vad.set_mode(1)  # 模式可以是 0, 1, 2, 3，其中 3 最为严格
        self.client = OpenAI()

    def transcribe_audio(self, audio_path):
        transcription = self.client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_path,
            response_format="text"
        )
        return transcription
    
    def process_audio_stream(self):
        # 设置 ffmpeg 命令
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

        #  
        process = subprocess.Popen(command, stdout=subprocess.PIPE)

        frame_duration = 10  # 每帧 1000 ms
        frame_width = 2 * 16000 * frame_duration // 1000  # 2 bytes per sample

        # 处理实时音频流
        audio_buffer = AudioSegment.empty()
        while True:
            data = process.stdout.read(frame_width)  # 假设320 bytes为10ms数据
            if not data:
                break
            is_speech = self.vad.is_speech(data, 16000)

            if is_speech:
                print("Speech detected")
                audio_segment = AudioSegment(data, sample_width=2, frame_rate=16000, channels=1)
                audio_buffer += audio_segment
            else:
                print("No speech detected")
                # 当检测到非语音帧时，如果缓冲区中有数据，进行处理
                if len(audio_buffer) > 0:
                    # 将 audio_buffer 传给 Whisper 进行识别
                    audio_data = audio_buffer.export(format="mp3")
                    audio_file = BytesIO(audio_data.read())

                    result =  self.model.transcribe(audio_file)
                    print(result["text"])
                    audio_buffer = AudioSegment.empty()  # 清空缓存

        # 确保处理完所有数据
        
        if len(audio_buffer) > 0:
            audio_data = audio_buffer.export(format="mp3")
            audio_file = BytesIO(audio_data.read())
            audio_file.name = "audio.mp3"  # OpenAI API 需要文件名
            result = self.transcribe_audio(audio_file)
            print(result.text)  # 假設 transcription 返回一個帶有 text 屬性的對象
            audio_buffer = AudioSegment.empty()

        process.wait()
        '''
        # 启动 ffmpeg 进程
        process = subprocess.Popen(command, stdout=subprocess.PIPE)

        frame_duration = 10  # 每帧 10 ms
        frame_width = 2 * 16000 * frame_duration // 1000  # 2 bytes per sample

        buffer = b""
        while True:
            # 读取数据
            in_data = process.stdout.read(frame_width)
            if not in_data:
                break
            buffer += in_data

            # 处理每个帧
            if len(buffer) >= frame_width:
                # 检查是否语音
                is_speech = self.vad.is_speech(buffer[:frame_width], 16000)
                print('Is speech: ', is_speech)
                buffer = buffer[frame_width:]

        # 关闭进程
        process.stdout.close()
        process.wait()

        '''


class AudioRecorder:
    def __init__(self, output_filename, output_directory, transcriptions = False):
        self.output_filename = output_filename
        self.output_directory = output_directory
        self.process = None
        self.stop_recording_flag = False
        self.segment_number = 0
        self.full_audio = AudioSegment.empty()
        self.client = None
        self.transcriptions = transcriptions
        if self.transcriptions:
            self.client = OpenAI()

    def record_audio(self):
        command = [
            'ffmpeg',
            '-f', 'avfoundation',  # 對於 macOS, 如果是 Windows 使用 'dshow'
            '-i', ':0',            # 對於 macOS, 如果是 Windows 使用 'audio=Microphone'
            '-acodec', 'pcm_s16le',
            '-ar', '44100',
            '-ac', '1',
            '-filter:a', 'volume=50.0',  # 增加音量，這裡的值可以根據需要調整
            '-f', 'wav',
            'pipe:1'
        ]
        print("FFmpeg command:", ' '.join(command))

        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**8)
        return self.process

    def save_segment(self, audio):
        segment_filename = os.path.join(self.output_directory, f"segment_{self.segment_number}.mp3")
        audio.export(segment_filename, format="mp3")
        self.segment_number += 1
        print(f"\nSaved segment: {segment_filename}")
        return segment_filename

    def start_recording(self):
        self.stop_recording_flag = False
        self.segment_number = 0

        self.process = self.record_audio()
        temp_audio = AudioSegment.empty()

        try:
            while not self.stop_recording_flag:
                raw_audio = self.process.stdout.read(4096)
                if not raw_audio:
                    break

                segment = AudioSegment(
                    raw_audio,
                    sample_width=2,
                    frame_rate=44100,
                    channels=1
                )
                temp_audio += segment
                self.full_audio += segment

                if len(temp_audio) >= 5000:  # 每 10 秒保存一次
                    #breakpoint()
                    segment_filename = self.save_segment(temp_audio)
                    temp_audio = AudioSegment.empty()
                    if self.transcriptions:
                        #breakpoint()
                        transcription = self.transcribe_audio(segment_filename)
                        print(transcription.text)

        except Exception as e:
            print(f"Exception occurred: {e}")
            self.stop_recording()

        # 保存最後剩餘的音頻片段
        if len(temp_audio) > 0:
            self.save_segment(temp_audio)

        # 保存整個錄音文件
        self.full_audio.export(self.output_filename, format="mp3")

        return self.process

    def stop_recording(self):
        self.stop_recording_flag = True

        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.write(b'q\n')
            except ValueError:
                print("Process stdin already closed")

        try:
            if self.process:
                self.process.stdin.close()
                self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if self.process:
                self.process.terminate()
                self.process.wait()

        stderr_output = self.process.stderr.read() if self.process else ""
        print("\nFFmpeg stderr output:\n", stderr_output)
        print("\nRecording stopped.")

    def signal_handler(self, sig, frame):
        self.stop_recording()
        sys.exit(0)

    def transcribe_audio(self, audio_path):
        audio_file= open(audio_path, "rb")
        transcription = self.client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file
        )
        return transcription

if __name__ == "__main__":
    if False:
        if len(sys.argv) != 3:
            print(f"Usage: python {sys.argv[0]} output.mp3 output_directory")
            sys.exit(1)

        output_filename = sys.argv[1]
        output_directory = sys.argv[2]

        if not os.path.exists(output_directory):
            os.makedirs(output_directory)

        recorder = AudioRecorder(output_filename, output_directory)
        signal.signal(signal.SIGINT, recorder.signal_handler)

        print("Press Ctrl+C to stop the recording.")
        recorder.start_recording()

        while True:
            time.sleep(1)
    else:
        client = AudioStream()
        client.process_audio_stream()