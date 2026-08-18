"""
CLI voice interface for the job search agent. Talks about your full queue
(every listing ever scored, from jobs.db - the same data and the same
"job N" numbering the web dashboard uses) and can tailor your CV to a
specific listing on request.

Say things like:
  "what's new" / "read the digest"   -> reads your queue aloud, highest fit first
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
import re

from dotenv import load_dotenv
from groq import Groq

import db
from cv_tailor import load_cv, save_suggestions, tailor_for_job

JOB_NUMBER_RE = re.compile(r"\b(?:job|listing|number)\s*(\d+)\b")


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

    words = re.findall(r"[a-z']+", text)
    if any(w in words for w in ("hi", "hello", "hey", "yo", "sup", "thanks", "thank")):
        return "greeting", None

    return "unknown", None


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def handle_command(
    intent: str,
    job_number: int | None,
    jobs: list[dict],
    client: Groq | None,
    cv_text: str | None,
) -> str:
    if intent == "greeting":
        if not jobs:
            return "Hey! Your queue's empty right now — run main.py to fetch and score some listings, then come back and ask me what's new."
        return (
            f"Hey! You've got {_plural(len(jobs), 'listing')} in your queue. "
            "Want me to run through what's new, or ask about a specific one?"
        )

    if intent == "digest":
        if not jobs:
            return "Your queue's empty right now — run main.py to fetch and score some listings, then come back and ask me."
        top = jobs[0]
        parts = [
            f"You've got {_plural(len(jobs), 'listing')} in your queue. The best one right now is "
            f"{top['title']} at {top['company']} — {top['score']} out of 10. {top['reason']}"
        ]
        for i, j in enumerate(jobs[1:], start=2):
            parts.append(f"Job {i}: {j['title']} at {j['company']}, {j['score']} out of 10.")
        return " ".join(parts)

    if intent in ("details", "tailor"):
        if job_number is None:
            return "Sure — which job number did you mean?"
        if not (1 <= job_number <= len(jobs)):
            return f"Hmm, I've only got {_plural(len(jobs), 'listing')} in your queue — job {job_number} isn't one of them."

    if intent == "details":
        job = jobs[job_number - 1]
        return (
            f"Job {job_number} is {job['title']} at {job['company']}, based in {job['location']}. "
            f"I'd give it {job['score']} out of 10 — {job['reason']}"
        )

    if intent == "tailor":
        if not cv_text:
            return "I can't find your CV yet — add your real CV content to cv.md and I'll be able to tailor it for you."
        if client is None:
            return "I'd love to help with that, but my Groq API key isn't set up yet — add GROQ_API_KEY to your .env and I'll be ready."
        job = jobs[job_number - 1]
        suggestions = tailor_for_job(client, cv_text, job)
        if "error" in suggestions:
            return f"That one didn't go through cleanly: {suggestions['error']}"
        path = save_suggestions(job, suggestions)
        top = ", ".join(suggestions.get("top_requirements", [])[:3])
        n_bullets = len(suggestions.get("bullet_suggestions", []))
        return (
            f"Done! For job {job_number}, the things that matter most are {top}. "
            f"I've written {n_bullets} tailored bullet suggestions and an opening line for you, saved to {path}."
        )

    return "Sorry, I didn't quite catch that — try something like 'what's new', 'tell me about job 2', or 'tailor my CV for job 2'."


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

    jobs = db.get_all_jobs()
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
        f"Hey! You've got {_plural(len(jobs), 'listing')} in your queue. "
        "Say what's new to hear them, or quit whenever you want to stop.",
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
