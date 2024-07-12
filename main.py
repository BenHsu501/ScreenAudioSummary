import os
import sys
import time
import threading
import subprocess
import signal
import platform

import ffmpeg

stop_ticker = False

def display_ticker():
    start_time = time.time()
    while not stop_ticker:
        elapsed_time = time.time() - start_time
        minutes, seconds = divmod(int(elapsed_time), 60)
        sys.stdout.write(f'\rRecording: {minutes:02d}:{seconds:02d}')
        sys.stdout.flush()
        time.sleep(1)

def start_recording(output_filename):
    global stop_ticker
    stop_ticker = False
    ticker_thread = threading.Thread(target=display_ticker)
    ticker_thread.start()

    # Detect the operating system and choose the appropriate ffmpeg input
    system = platform.system()
    if system == "Windows":
        input_device = ffmpeg.input('default', format='dshow', ac=1, ar='44100')
    elif system == "Darwin":  # macOS
        input_device = ffmpeg.input(':0', format='avfoundation', ac=1, ar='44100')
    else:
        raise RuntimeError(f"Unsupported operating system: {system}")

    # The command to record audio using FFmpeg
    stream = (
        input_device
        .output(output_filename, acodec='libmp3lame', format='mp3')
        .overwrite_output()
        .compile()
    )

    print("FFmpeg command:", ' '.join(stream))
    
    process = subprocess.Popen(stream, stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    return process

def stop_recording(process):
    global stop_ticker
    stop_ticker = True

    if process.poll() is None:  # Check if the process is still running
        process.stdin.write('q\n')  # Send 'q' to gracefully stop ffmpeg
        process.stdin.flush()

    try:
        process.stdin.close()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait()

    stderr_output = process.stderr.read()
    print("\nFFmpeg stderr output:\n", stderr_output)
    print("\nRecording stopped.")

def signal_handler(sig, frame):
    stop_recording(process)
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} output.mp3")
        sys.exit(1)

    output_filename = sys.argv[1]

    signal.signal(signal.SIGINT, signal_handler)

    process = start_recording(output_filename)
    print("Press Ctrl+C to stop the recording.")

    # Keep the main thread alive, waiting for the signal to stop recording
    while True:
        time.sleep(1)
