"""
CLI voice interface for the job search agent. Talks about your most recent
run (from last_run.json, written by main.py) and can tailor your CV to a
specific listing on request.

Say things like:
  "what's new" / "read the digest"   -> reads today's scored listings aloud
  "tell me about job 2"              -> reads full details for listing #2
  "tailor my cv for job 2"           -> tailors your CV to listing #2, speaks
                                         a short summary, writes the full
                                         write-up to cv_suggestions/
  "quit" / "exit" / "stop"           -> ends the session

Requires a microphone and speakers, plus:
    pip install -r requirements-voice.txt
Uses SpeechRecognition (free Google speech-to-text, no API key) for
listening and pyttsx3 (offline, your OS's native voice) for speaking.

No microphone/speakers? Use text mode instead:
    python voice_agent.py --text
"""

import argparse
import json
import re
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from cv_tailor import load_cv, save_suggestions, tailor_for_job

LAST_RUN_PATH = Path(__file__).parent / "last_run.json"

JOB_NUMBER_RE = re.compile(r"\b(?:job|listing|number)\s*(\d+)\b")


def load_last_run() -> list[dict]:
    if not LAST_RUN_PATH.exists():
        return []
    return json.loads(LAST_RUN_PATH.read_text())


def parse_command(text: str) -> tuple[str, int | None]:
    """Turn free-form text into (intent, job_number). Pure function, no audio - easy to test."""
    text = text.lower().strip()

    if any(w in text for w in ("quit", "exit", "stop", "goodbye", "bye")):
        return "quit", None

    match = JOB_NUMBER_RE.search(text)
    job_number = int(match.group(1)) if match else None

    if any(w in text for w in ("tailor", "cv", "resume", "cover letter")):
        return "tailor", job_number

    if job_number is not None:
        return "details", job_number

    if any(w in text for w in ("digest", "what's new", "whats new", "today", "new jobs", "list")):
        return "digest", None

    return "unknown", None


def handle_command(
    intent: str,
    job_number: int | None,
    jobs: list[dict],
    client: Groq | None,
    cv_text: str | None,
) -> str:
    if intent == "digest":
        if not jobs:
            return "There's nothing in today's digest yet. Run main.py first."
        lines = [f"You have {len(jobs)} new listings today."]
        for i, j in enumerate(jobs, start=1):
            lines.append(f"Job {i}: {j['title']} at {j['company']}, score {j['score']} out of 10.")
        return " ".join(lines)

    if intent in ("details", "tailor"):
        if job_number is None:
            return "Which job number did you mean?"
        if not (1 <= job_number <= len(jobs)):
            return f"I only have {len(jobs)} listings today, job {job_number} doesn't exist."

    if intent == "details":
        job = jobs[job_number - 1]
        return (
            f"Job {job_number}: {job['title']} at {job['company']}, {job['location']}. "
            f"Score {job['score']} out of 10. {job['reason']}"
        )

    if intent == "tailor":
        if not cv_text:
            return "I couldn't find your CV. Fill in cv.md with your CV content first."
        if client is None:
            return "Groq API key isn't configured. Add GROQ_API_KEY to .env to use CV tailoring."
        job = jobs[job_number - 1]
        suggestions = tailor_for_job(client, cv_text, job)
        if "error" in suggestions:
            return f"Something went wrong tailoring that one: {suggestions['error']}"
        path = save_suggestions(job, suggestions, job_number)
        top = ", ".join(suggestions.get("top_requirements", [])[:3])
        n_bullets = len(suggestions.get("bullet_suggestions", []))
        return (
            f"Done. The top requirements for job {job_number} are {top}. "
            f"I've written {n_bullets} tailored bullet suggestions and an opening line to {path}."
        )

    return "I didn't catch a command. Try 'what's new', 'tell me about job 2', or 'tailor my CV for job 2'."


def speak(text: str, tts_engine) -> None:
    print(f"AGENT: {text}")
    if tts_engine is not None:
        tts_engine.say(text)
        tts_engine.runAndWait()


def listen(recognizer, microphone) -> str | None:
    with microphone as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("Listening...")
        audio = recognizer.listen(source)
    try:
        return recognizer.recognize_google(audio)
    except Exception as e:
        print(f"(didn't catch that: {e})")
        return None


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Voice interface for the job search agent.")
    parser.add_argument("--text", action="store_true", help="Type commands instead of speaking (no mic/speaker needed)")
    args = parser.parse_args()

    jobs = load_last_run()
    try:
        client = Groq()
    except Exception:
        client = None
    try:
        cv_text = load_cv()
    except FileNotFoundError:
        cv_text = None

    tts_engine = None
    recognizer = microphone = None

    if not args.text:
        import pyttsx3
        import speech_recognition as sr

        tts_engine = pyttsx3.init()
        recognizer = sr.Recognizer()
        microphone = sr.Microphone()

    speak(
        f"Hi. You have {len(jobs)} listings from your last run. "
        "Say what's new to hear them, or quit to stop.",
        tts_engine,
    )

    while True:
        if args.text:
            text = input("YOU: ").strip()
        else:
            text = listen(recognizer, microphone)
            if text is None:
                continue
            print(f"YOU: {text}")

        if not text:
            continue

        intent, job_number = parse_command(text)
        if intent == "quit":
            speak("Goodbye.", tts_engine)
            break

        response = handle_command(intent, job_number, jobs, client, cv_text)
        speak(response, tts_engine)


if __name__ == "__main__":
    main()
