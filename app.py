"""YouTube Quiz Generator

Paste a YouTube link. The app fetches the video transcript and asks a Groq-hosted
LLM to write multiple-choice questions based on it.

Run:  python app.py   (then open http://127.0.0.1:5000)
"""

import json
import os
import re

from flask import Flask, jsonify, render_template, request
from groq import Groq
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

try:  # optional: load GROQ_API_KEY from a local .env file
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
MAX_TRANSCRIPT_CHARS = 12000   # keep the prompt small enough for the model
MIN_TRANSCRIPT_CHARS = 200     # too short to make a useful quiz
MIN_QUESTIONS, MAX_QUESTIONS = 3, 10

VIDEO_ID_PATTERNS = [
    r"(?:youtube\.com/watch\?(?:.*&)?v=)([A-Za-z0-9_-]{11})",
    r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/(?:embed|shorts|live)/)([A-Za-z0-9_-]{11})",
]


class QuizError(Exception):
    """An error with a message that is safe to show to the user."""


# ---------------------------------------------------------------- transcript
def extract_video_id(url):
    url = (url or "").strip()
    for pattern in VIDEO_ID_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):  # a bare video id
        return url
    raise QuizError("That doesn't look like a valid YouTube link.")


def fetch_transcript(video_id):
    api = YouTubeTranscriptApi()
    try:
        try:
            fetched = api.fetch(video_id, languages=["en", "en-US", "en-GB", "en-IN"])
        except NoTranscriptFound:
            # No English track: fall back to whatever language is available.
            fetched = next(iter(api.list(video_id))).fetch()
    except TranscriptsDisabled:
        raise QuizError("This video has transcripts turned off.")
    except VideoUnavailable:
        raise QuizError("This video is unavailable.")
    except NoTranscriptFound:
        raise QuizError("No transcript was found for this video.")
    except StopIteration:
        raise QuizError("No transcript was found for this video.")
    except Exception as exc:
        raise QuizError(f"Could not fetch the transcript: {exc}")

    text = " ".join(snippet.text.replace("\n", " ") for snippet in fetched)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < MIN_TRANSCRIPT_CHARS:
        raise QuizError("The transcript is too short to make a quiz from.")
    return text


def shrink_transcript(text, limit=MAX_TRANSCRIPT_CHARS):
    """If the transcript is long, keep the start, middle and end so the quiz
    covers the whole video instead of only the first few minutes."""
    if len(text) <= limit:
        return text
    part = limit // 3
    middle_start = (len(text) - part) // 2
    return " ... ".join([
        text[:part],
        text[middle_start:middle_start + part],
        text[-part:],
    ])


# ---------------------------------------------------------------------- quiz
def build_prompt(transcript, count):
    return f"""You are a teacher writing a quiz from a video transcript.

Write exactly {count} multiple-choice questions that test understanding of the main ideas in the transcript.
Rules:
- Use only information from the transcript.
- Each question has exactly 4 options and exactly one correct answer.
- Make the wrong options plausible, not silly.
- Spread the correct answer across positions A to D.
- Add a one-sentence explanation of why the answer is correct.

Return ONLY valid JSON in this shape:
{{"questions": [{{"question": "...", "options": ["...", "...", "...", "..."], "answer_index": 0, "explanation": "..."}}]}}

Transcript:
{transcript}"""


def clean_questions(data):
    """Check the model's output and drop anything malformed."""
    cleaned = []
    for item in data.get("questions", []):
        try:
            question = str(item["question"]).strip()
            options = [str(o).strip() for o in item["options"]]
            answer = int(item["answer_index"])
            explanation = str(item.get("explanation", "")).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if question and len(options) == 4 and all(options) and 0 <= answer < 4:
            cleaned.append({
                "question": question,
                "options": options,
                "answer_index": answer,
                "explanation": explanation,
            })
    return cleaned


def generate_questions(transcript, count):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise QuizError("The server has no GROQ_API_KEY set.")
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": build_prompt(transcript, count)}],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=4000,  # reasoning models spend part of this thinking
            extra_body={"reasoning_effort": "low"},
        )
        data = json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        raise QuizError("The AI returned an unreadable answer. Please try again.")
    except Exception as exc:
        raise QuizError(f"The AI service failed: {exc}")

    questions = clean_questions(data)
    if not questions:
        raise QuizError("The AI did not return any usable questions. Please try again.")
    return questions[:count]


# -------------------------------------------------------------------- routes
@app.get("/")
def index():
    return render_template("index.html", min_q=MIN_QUESTIONS, max_q=MAX_QUESTIONS)


@app.post("/api/quiz")
def api_quiz():
    body = request.get_json(silent=True) or {}
    try:
        count = int(body.get("num_questions", 5))
    except (TypeError, ValueError):
        count = 5
    count = max(MIN_QUESTIONS, min(MAX_QUESTIONS, count))

    try:
        video_id = extract_video_id(body.get("url"))
        transcript = shrink_transcript(fetch_transcript(video_id))
        questions = generate_questions(transcript, count)
    except QuizError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"video_id": video_id, "questions": questions})


if __name__ == "__main__":
    app.run(debug=True)
