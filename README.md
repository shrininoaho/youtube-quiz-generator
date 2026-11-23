# YouTube Quiz Generator
A web app that turns any YouTube video into a multiple-choice quiz. Paste a link, and it reads the video's transcript and asks an AI model (Groq) to write questions with four options, the correct answer and a short explanation.

## How it works
YouTube link → video ID → transcript (`youtube-transcript-api`) → prompt to Groq (`openai/gpt-oss-20b`, JSON mode) → validated questions → quiz in the browser

- Long transcripts are trimmed to their start, middle and end, so the quiz covers the whole video.
- The server checks every question the model returns and drops any that are malformed.
- Answers are checked in the browser, with the explanation shown for each question.

## Tech
Python, Flask, HTML, CSS, JavaScript, Groq API

## Run it
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put your Groq API key in .env
python app.py
```
Open http://127.0.0.1:5000

Get a free key at https://console.groq.com. Never commit your `.env` file (it is already in `.gitignore`).

## Limitations
- Only works for videos that have a transcript (captions).
- Question quality depends on the model, so some questions may need a second look.
- The `youtube-transcript-api` library can be blocked by YouTube on some cloud hosts.
- This is a rebuild of an earlier course mini project.
