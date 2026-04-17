"""offer_choices tool -- presents tap-able options to the user.

On Telegram this renders as an InlineKeyboardMarkup. On the dashboard it can
be rendered as a row of buttons. Either way, after this tool is called the
agent must stop and wait for the user to pick a choice.
"""

import json

from langchain_core.tools import tool


@tool
def offer_choices(prompt: str, options: list[str]) -> str:
    """Present the user with a short list of tap-able choices.

    Use this INSTEAD of writing a plain numbered list whenever the user is
    likely to pick one and keep going (e.g. "which note should I read?",
    "which scene?", "which episode?"). The runtime renders ``options`` as
    tap-able buttons on Telegram, and as a button row on the dashboard.

    Args:
        prompt: A 1-2 line message explaining what to choose. Keep it short;
            the user already sees the buttons.
        options: 2-8 short option labels (max 56 characters each). Each label
            becomes a tap-able button; tapping posts the label back as the
            user's next message.

    IMPORTANT: After calling this tool you must END YOUR TURN. Do not generate
    any additional text or further tool calls -- the user's tap is the next
    thing that should happen in the conversation. The runtime already shows
    ``prompt`` together with the buttons, so an extra message is noise.
    """
    cleaned = [str(o).strip() for o in options if str(o).strip()]
    return json.dumps({
        "status": "presented",
        "prompt": prompt,
        "options": cleaned[:8],
    })


def get_choices_tools() -> list:
    return [offer_choices]
