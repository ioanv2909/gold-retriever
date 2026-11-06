"""Mesaje de atentionare ca un card colorat (fundal + bara in stanga), in locul casetei galbene st.warning.
Textul se escapeaza; din markdown se pastreaza doar **bold** si `cod`."""
import html
import re

import streamlit as st

ACCENT = "#22b8cf"  # turcoaz, ales de utilizator; galbenul st.warning nu se mai foloseste


def card_html(text, icon="⚠️", color=ACCENT):
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    body = html.escape(str(text))
    body = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", body)
    body = re.sub(r"`(.+?)`", r"<code>\1</code>", body)
    body = body.replace("\n", "<br>")
    return ('<div class="gr-notice" style="background:rgba(%d,%d,%d,0.22);border-left:4px solid %s;'
            'border-radius:0.5rem;padding:0.75rem 1rem;margin-bottom:1rem;line-height:1.5">%s%s</div>'
            % (r, g, b, color, (icon + " ") if icon else "", body))


def card(text, icon="⚠️", color=ACCENT, where=None):
    """Afiseaza cardul (in where, daca e dat: o coloana sau un container)."""
    (where or st).markdown(card_html(text, icon, color), unsafe_allow_html=True)
