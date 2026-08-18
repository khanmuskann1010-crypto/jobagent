"""
Runs a mock interview for growth marketing roles - the same job family
this whole app screens listings for (see profile.md). A separate, simpler
conversation loop from chat_agent.py: no tools, just Dextor playing
interviewer one question at a time, grounded loosely in the candidate's
real CV so questions feel specific rather than generic.
"""

from groq import Groq

from groq_errors import friendly_groq_error

MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT_TEMPLATE = """You are Dextor, running a mock job interview with a candidate for a \
growth marketing role - channels, funnels, CAC/LTV, campaign strategy, A/B testing, attribution, \
growth loops, stakeholder and budget communication. You are warm but genuinely rigorous, like a \
real hiring manager, not a rubber stamp.

Rules:
- Ask ONE question at a time. Never dump multiple questions in one message.
- After the candidate answers, give brief (1-2 sentence) honest feedback - what landed, what a \
stronger answer would include - THEN ask the next question.
- Mix question types across the session: background/experience, a scenario/case question \
("how would you grow X"), a metrics/analytical question, and a behavioral question.
- Stay strictly within growth marketing interview territory - don't drift into unrelated roles.
- Keep each message conversational and reasonably brief, like real interview dialogue, not an essay.
- If the candidate asks to end/wrap up, close warmly with 1-2 sentences of overall feedback.

{cv_context}

This is the very first message of the session: greet them briefly and ask your first question."""


def _system_prompt(cv_text: str | None) -> str:
    cv_context = (
        f"Here is the candidate's real CV, for grounding your questions in their actual "
        f"experience (don't invent anything about them beyond this):\n{cv_text}"
        if cv_text else
        "No CV is on file, so keep questions general to growth marketing rather than "
        "referencing specific experience."
    )
    return SYSTEM_PROMPT_TEMPLATE.format(cv_context=cv_context)


def interview_turn(client: Groq | None, history: list[dict], cv_text: str | None) -> str:
    """history is [{"role": "user"|"assistant", "content": str}, ...] - empty on the very
    first call, which is what triggers Dextor's opening greeting + first question."""
    if client is None:
        return (
            "I'd love to run this with you, but my Groq API key isn't set up yet — "
            "add GROQ_API_KEY to your .env and I'll be ready."
        )

    messages = [{"role": "system", "content": _system_prompt(cv_text)}]
    messages += history if history else [{"role": "user", "content": "Let's begin."}]

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=500,
            reasoning_effort="low",
        )
        return response.choices[0].message.content or "..."
    except Exception as e:
        return friendly_groq_error(e)
