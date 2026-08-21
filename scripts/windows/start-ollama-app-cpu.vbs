' Start Ollama app in GPU mode (RTX 4060)
' The CUDA crash (0xc0000409) on driver 595.97 is fixed - no CPU workaround needed.
' Model runs fully on GPU (36/37 layers) at ~25 tokens/s.
Set sh = CreateObject("WScript.Shell")
sh.Run """C:\Users\yang\AppData\Local\Programs\Ollama\ollama app.exe""", 0, False
