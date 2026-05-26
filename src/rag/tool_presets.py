"""Document tool action presets (strict, from index only)."""

from __future__ import annotations

TOOL_ACTIONS: dict[str, dict[str, str]] = {
    "summarize": {
        "label": "Summarize document",
        "prompt": (
            "Provide a clear, structured summary of the document content. "
            "Use short paragraphs. Do not mention file names or bracketed citations."
        ),
    },
    "bullet_points": {
        "label": "Extract topics",
        "prompt": (
            "List the main topics and themes (about 8–12 bullets). "
            "One bullet per line starting with •. "
            "Each bullet: at most 2 short sentences or about 25 words. "
            "No file names, no markdown, no bracketed citations."
        ),
    },
    "study_questions": {
        "label": "Question generator",
        "prompt": (
            "Generate 10–14 study or exam-style questions based only on the documents. "
            "Mix short-answer and conceptual questions. Number them. "
            "Do not mention file names or bracketed citations."
        ),
    },
    "conclusion": {
        "label": "Document insights",
        "prompt": (
            "Write an insights section based only on the documents: "
            "key takeaways, risks, opportunities, and closing observations. "
            "Do not mention file names or bracketed citations."
        ),
    },
    "index": {
        "label": "Text extractor",
        "prompt": (
            "Create a table-of-contents style outline of the document: "
            "numbered or bulleted sections with brief labels. "
            "Reflect structure found in the text. "
            "Do not mention file names or bracketed citations."
        ),
    },
    "headings": {
        "label": "Citation finder",
        "prompt": (
            "List notable claims or statements that would need citations in a paper: "
            "for each, give a short quote or paraphrase and the section idea. "
            "Use a numbered list. Do not mention file names or bracketed citations."
        ),
    },
    "keyword_focus": {
        "label": "Keyword finder",
        "prompt": (
            "Extract 18–25 important keywords and short phrases from the documents. "
            "One per line. No explanations. "
            "Do not mention file names or bracketed citations."
        ),
    },
}


def build_tool_prompt(action: str, custom: str = "") -> str:
    if action == "custom":
        return custom.strip() or "Answer using only the indexed documents."
    preset = TOOL_ACTIONS.get(action)
    if preset:
        return preset["prompt"]
    return custom.strip() or TOOL_ACTIONS["summarize"]["prompt"]


def list_tool_actions() -> list[dict[str, str]]:
    items = [{"id": k, "label": v["label"]} for k, v in TOOL_ACTIONS.items()]
    items.append({"id": "custom", "label": "Custom instruction"})
    return items
