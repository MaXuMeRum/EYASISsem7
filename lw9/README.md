# English Literature Essay Analyzer

A small Python desktop application for analyzing English literature essays.

## Features
- Select which operations the system should perform.
- Analyze essay text and display a notification/status message when analysis completes.
- Choose the analysis language (English is the supported language in this version).
- Optional microphone speech input that transcribes English speech and adds it to the essay.
- Open `.txt` essays and save analysis reports.

## Requirements
- Python 3.10 or newer
- Tkinter (usually included with standard Python installations)
- For speech input: install the packages in `requirements.txt`, a working microphone, and internet access for Google speech recognition.

## Run
```bash
python main.py
```

## Enable speech recognition
```bash
python -m pip install -r requirements.txt
```

On some Windows installations, installing PyAudio may require a compatible wheel or additional setup. The app still runs for typed/pasted essays without speech packages.

## How to use
1. Run `main.py`.
2. Select the analysis operations in the right-hand panel.
3. Enter or open an English literature essay.
4. Click **Analyze essay** to view the results.
5. To dictate text, click **Start speech input** and speak English. Click **Stop listening** when finished.
6. Use **Save report** to export the current results.

## Limitations
The analyzer uses simple rules and keyword matching. It does not provide an official grade, verify quotations, detect plagiarism, or deeply evaluate literary interpretation.
