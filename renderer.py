from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import BASE_DIR, TMP_DIR
from handlers.common import ticket_image_count
from parser import parse_raw_text


async def render_tickets(tickets: list[dict]) -> str:
    fragments = [
        parse_raw_text(
            ticket["raw_text"],
            bool(ticket["has_image"]),
            image_count=ticket_image_count(ticket["id"]),
        )
        for ticket in tickets
    ]

    env = Environment(
        loader=FileSystemLoader(BASE_DIR / "templates"),
        autoescape=select_autoescape(("html", "xml")),
    )
    template = env.get_template("base.html")
    html_content = template.render(fragments=fragments)

    tmp_dir = Path(TMP_DIR)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    output_path = tmp_dir / f"tickets_{uuid4().hex[:8]}.html"
    output_path.write_text(html_content, encoding="utf-8")
    return str(output_path)
