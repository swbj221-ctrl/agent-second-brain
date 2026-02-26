import subprocess

text = "Hello world"

result = subprocess.run(
    [
        r".\piper\piper_windows_amd64\piper\piper.exe",
        "--model",
        r".\voices_piper\en_GB-jenny_dico-medium.onnx",
        "--output_file",
        "out.wav",
    ],
    input=text.encode("utf-8"),
)

print("Return code:", result.returncode)