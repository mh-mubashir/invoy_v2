"""
Invoy App — Claude API work-log summariser.

Takes the full list of activity descriptions from a session and calls
claude-opus-4-5 to cluster them into logical work categories (not time-ordered).
The result is Markdown-formatted text rendered in the SummaryPanel.

Designed to run in a daemon thread; communicates back via callbacks.
"""

from __future__ import annotations

import threading
from typing import Callable


# ── Prompt ─────────────────────────────────────────────────────────────────

_SUMMARY_PROMPT = """\
You are a work-log generator for a software developer.
Below is a chronological list of short activity descriptions captured from the person's screen during a work session.

Your task:
1. Read through all activities.
2. Identify the distinct categories of work (e.g. "Code Review", "Python Development", "Research / Web Browsing", "Communication", "Documentation").
3. For each category, write 2-5 concise bullet points summarising what was done.
4. Do NOT organise by time — group by TYPE of work.
5. Be specific: name files, tools, URLs, or topics that appear in the descriptions.
6. Keep each bullet under 20 words.

Format your response exactly as:

## [Category Name]
- [bullet]
- [bullet]

## [Category Name]
- [bullet]

---
Activity descriptions ({n} frames):
{activities}
"""


# ── ClaudeSummariser ────────────────────────────────────────────────────────

class ClaudeSummarizer:
    """
    Calls the Anthropic Claude API to produce a structured work log.

    Parameters
    ----------
    api_key : str
        Anthropic API key.  If empty, ``summarize()`` immediately calls ``on_error``.
    model : str
        Claude model ID.  Defaults to ``claude-opus-4-5``.
    max_tokens : int
        Maximum response tokens.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-opus-4-5",
        max_tokens: int = 1500,
    ) -> None:
        self._api_key   = api_key
        self._model     = model
        self._max_tokens = max_tokens

    # ── Public ─────────────────────────────────────────────────────────

    def update_api_key(self, api_key: str) -> None:
        """Update the API key at runtime (called after Settings save)."""
        self._api_key = api_key

    def summarize(
        self,
        entries: list[dict],
        on_complete: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        """
        Kick off an async summarisation.  Returns immediately.

        ``on_complete(text)`` and ``on_error(message)`` are called from a
        daemon thread — callers must marshal back to the Tk thread via
        ``root.after(0, ...)`` before touching widgets.
        """
        if not self._api_key:
            on_error("No Claude API key configured. Open Settings to add one.")
            return
        if not entries:
            on_error("No activity entries to summarise — start a recording session first.")
            return

        thread = threading.Thread(
            target=self._run,
            args=(entries, on_complete, on_error),
            daemon=True,
        )
        thread.start()

    # ── Internal ────────────────────────────────────────────────────────

    def _run(
        self,
        entries: list[dict],
        on_complete: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        try:
            import anthropic  # type: ignore  # optional dep
        except ImportError:
            on_error(
                "The 'anthropic' package is not installed.\n"
                "Run: pip install anthropic"
            )
            return

        # Build numbered activity list
        activities: list[str] = []
        for e in entries:
            text = (e.get("activity") or e.get("activity_text") or "").strip()
            if text:
                activities.append(text)

        if not activities:
            on_error("No activity text found in the session entries.")
            return

        numbered = "\n".join(f"{i+1}. {a}" for i, a in enumerate(activities))
        prompt   = _SUMMARY_PROMPT.format(n=len(activities), activities=numbered)

        try:
            client = anthropic.Anthropic(api_key=self._api_key)
            message = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            result_text = message.content[0].text
            on_complete(result_text)
        except anthropic.AuthenticationError:
            on_error("Invalid Claude API key. Check Settings.")
        except anthropic.RateLimitError:
            on_error("Claude API rate limit reached. Please wait and try again.")
        except Exception as exc:
            on_error(f"Claude API error: {exc}")
