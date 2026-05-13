"""
Autobiografie Assistent — Streamlit webinterface
"""

import os
import json
from datetime import datetime
from pathlib import Path

import streamlit as st
import anthropic
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Constanten
# ---------------------------------------------------------------------------

MODEL = "claude-opus-4-7"
OUTPUT_DIR = Path("autobiografieën")
CHUNK_SIZE = 6  # berichten per chunk (3 vragen + 3 antwoorden)

INTERVIEW_SYSTEM_PROMPT = """Je bent een warme, empathische autobiografie-interviewer die mensen helpt hun levensverhaal te ontdekken en te vertellen. Je bent tegelijkertijd journalist, therapeut en schrijver — nieuwsgierig, geduldig en creatief.

**Jouw doel:** door slimme vragen de mooiste, meest menselijke en meest betekenisvolle momenten uit iemands leven naar boven halen — momenten die de persoon misschien zelf al vergeten was of nooit zo had verwoord.

**Aanpak:**
- Begin met brede, open vragen om een beeld te krijgen van de persoon
- Verdiep je ALTIJD in interessante details die worden genoemd — vraag door
- Vraag naar emoties, gedachten, geuren, kleuren, geluiden — maak herinneringen levendig
- Ontdek de "waarom" achter keuzes en levensgebeurtenissen
- Verbind thema's: "Je noemde eerder X — hoe past dat bij wat je nu vertelt?"
- Stel vragen die mensen aan het denken zetten: "Wat zou jij je 20-jarige zelf willen zeggen?"

**Regels:**
- Stel ALTIJD slechts ÉÉN vraag per bericht
- Reageer eerst warm en samengevat op wat de persoon deelde, dan pas de nieuwe vraag
- Ga niet te snel — laat de persoon uitweiden
- Bij emotionele onderwerpen: erken eerst, vraag daarna voorzichtig door
- Gebruik de naam van de persoon als je die kent

**Thema's om te verkennen** (niet allemaal tegelijk, maar geleidelijk):
- Jeugd en herkomst: ouders, woonplaats, herinneringen, school
- Bepalende momenten: keuzes die alles veranderden
- Relaties: vriendschappen, liefde, verlies
- Passies en talenten: wat maakt deze persoon uniek?
- Uitdagingen: hoe zijn ze overwonnen?
- Dromen: wat heeft deze persoon nagestreefd?
- Erfenis: wat wil deze persoon achterlaten?

Begin met een hartelijke begroeting en een eerste, open vraag."""


CHAPTER_SYSTEM_PROMPT = """Je bent een professionele biografieschrijver. Je krijgt een fragment van een autobiografie-interview en schrijft er één hoofdstuk van een autobiografie van.

Richtlijnen:
- Schrijf in de eerste persoon ("Ik...")
- Warme, literaire toon — geen droge opsomming
- Verwerk concrete details, anekdotes en emoties uit het fragment
- Maak het levendig: laat de lezer de momenten beleven
- Geef het hoofdstuk een passende, poëtische titel
- Lengte: 300–600 woorden

Formaat — geef ALLEEN dit terug, niets anders:
## [Hoofdstuktitel]

[Hoofdstukinhoud]"""


ASSEMBLY_SYSTEM_PROMPT = """Je bent een professionele redacteur die losse hoofdstukken samenvoegt tot één vloeiende autobiografie.

Jouw taak:
- Verbind de hoofdstukken tot een samenhangend geheel
- Voeg een korte inleiding toe (max 100 woorden)
- Voeg een afsluitende passage toe over erfenis of toekomstblik
- Zorg voor vloeiende overgangen tussen hoofdstukken
- Verander de inhoud van de hoofdstukken zo min mogelijk — behoud de stem
- Schrijf in de eerste persoon

Geef de volledige autobiografie terug, inclusief alle hoofdstukken."""


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------

def get_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY") or st.session_state.get("api_key", "")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def get_real_messages(messages):
    """Berichten zonder de starter-prompt."""
    return [m for m in messages if m["content"] != "Laten we beginnen."]


def get_chunks(messages):
    """Splits berichten in chunks van CHUNK_SIZE."""
    real = get_real_messages(messages)
    chunks = []
    for i in range(0, len(real), CHUNK_SIZE):
        chunks.append(real[i:i + CHUNK_SIZE])
    return chunks


def chunk_is_complete(chunk_index, messages):
    """Een chunk is compleet als er een volgende chunk is begonnen."""
    chunks = get_chunks(messages)
    return chunk_index < len(chunks) - 1


def autosave(messages, chapters):
    """Sla automatisch op na elke beurt."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    base_name = st.session_state.get("base_name", datetime.now().strftime("%Y%m%d_%H%M%S"))
    json_path = OUTPUT_DIR / f"data_{base_name}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "created_at": datetime.now().isoformat(),
            "messages": messages,
            "chapters": chapters,
        }, f, ensure_ascii=False, indent=2)


def save_autobiography(text, base_name):
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / f"autobiografie_{base_name}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write("MIJN AUTOBIOGRAFIE\n")
        f.write(f"Gegenereerd op: {datetime.now().strftime('%d %B %Y')}\n")
        f.write("=" * 60 + "\n\n")
        f.write(text)
    return path


def generate_chapter(client, chunk_messages, chunk_index):
    """Genereer een hoofdstuk voor een chunk."""
    fragment = ""
    for msg in chunk_messages:
        role = "Interviewer" if msg["role"] == "assistant" else "Persoon"
        fragment += f"{role}: {msg['content']}\n\n"

    with client.messages.stream(
        model=MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=[{"type": "text", "text": CHAPTER_SYSTEM_PROMPT,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user",
                   "content": f"Schrijf een hoofdstuk op basis van dit interviewfragment:\n\n{fragment}"}],
    ) as stream:
        return stream.get_final_text()


def assemble_autobiography(client, chapters):
    """Samengestelde autobiografie van alle hoofdstukken."""
    all_chapters = "\n\n---\n\n".join(
        f"Hoofdstuk {i+1}:\n{ch}" for i, ch in enumerate(chapters)
    )
    with client.messages.stream(
        model=MODEL,
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=[{"type": "text", "text": ASSEMBLY_SYSTEM_PROMPT,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user",
                   "content": f"Voeg deze hoofdstukken samen tot één autobiografie:\n\n{all_chapters}"}],
    ) as stream:
        return stream.get_final_text()


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Autobiografie Assistent",
    page_icon="📖",
    layout="wide",
)

st.markdown("""
<style>
    .block-container { max-width: 1100px; }
    h1 { font-size: 1.8rem !important; }
    .chapter-box {
        background: #1e1e2e;
        border-left: 3px solid #7c6af7;
        padding: 1rem 1.2rem;
        border-radius: 8px;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sessiestatus initialiseren
# ---------------------------------------------------------------------------

defaults = {
    "messages": [],
    "chapters": {},        # {chunk_index: chapter_text}
    "autobiography": None,
    "base_name": datetime.now().strftime("%Y%m%d_%H%M%S"),
    "started": False,
    "api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ---------------------------------------------------------------------------
# API-sleutel controleren
# ---------------------------------------------------------------------------

if not st.session_state.api_key:
    st.error("❌ Geen API-sleutel gevonden. Voeg `ANTHROPIC_API_KEY=sk-ant-...` toe aan het `.env` bestand.")
    st.stop()

client = get_client()

# ---------------------------------------------------------------------------
# Layout: twee kolommen
# ---------------------------------------------------------------------------

col_chat, col_book = st.columns([3, 2], gap="large")

# ---------------------------------------------------------------------------
# Linker kolom: het gesprek
# ---------------------------------------------------------------------------

with col_chat:
    st.title("📖 Autobiografie Assistent")
    st.caption("Claude stelt je vragen om jouw levensverhaal te ontdekken.")

    # Start het gesprek automatisch
    if not st.session_state.started:
        st.session_state.started = True
        with st.spinner("Claude bereidt zich voor..."):
            interview_system = [{"type": "text", "text": INTERVIEW_SYSTEM_PROMPT,
                                 "cache_control": {"type": "ephemeral"}}]
            with client.messages.stream(
                model=MODEL,
                max_tokens=1024,
                thinking={"type": "adaptive"},
                system=interview_system,
                messages=[{"role": "user", "content": "Laten we beginnen."}],
            ) as stream:
                opening = stream.get_final_text()
        st.session_state.messages.append({"role": "user", "content": "Laten we beginnen."})
        st.session_state.messages.append({"role": "assistant", "content": opening})
        autosave(st.session_state.messages, st.session_state.chapters)

    # Gespreksgeschiedenis
    for msg in st.session_state.messages:
        if msg["content"] == "Laten we beginnen.":
            continue
        role = "assistant" if msg["role"] == "assistant" else "user"
        with st.chat_message(role, avatar="📖" if role == "assistant" else "👤"):
            st.markdown(msg["content"])

    # Chat-invoer
    if prompt := st.chat_input("Jouw antwoord..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)

        interview_system = [{"type": "text", "text": INTERVIEW_SYSTEM_PROMPT,
                             "cache_control": {"type": "ephemeral"}}]
        with st.chat_message("assistant", avatar="📖"):
            placeholder = st.empty()
            full_response = ""
            with client.messages.stream(
                model=MODEL,
                max_tokens=1024,
                thinking={"type": "adaptive"},
                system=interview_system,
                messages=st.session_state.messages,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    placeholder.markdown(full_response + "▌")
            placeholder.markdown(full_response)

        st.session_state.messages.append({"role": "assistant", "content": full_response})
        autosave(st.session_state.messages, st.session_state.chapters)
        st.rerun()

# ---------------------------------------------------------------------------
# Rechter kolom: het boek
# ---------------------------------------------------------------------------

with col_book:
    st.subheader("📚 Jouw boek")

    chunks = get_chunks(st.session_state.messages)
    has_chapters = bool(st.session_state.chapters)

    if not chunks:
        st.caption("Nog geen gesprek om om te zetten.")
    else:
        for i, chunk in enumerate(chunks):
            is_complete = chunk_is_complete(i, st.session_state.messages)
            chapter_exists = i in st.session_state.chapters
            q_count = sum(1 for m in chunk if m["role"] == "user")

            label = f"Fragment {i + 1} · {q_count} vragen"
            status = "✅" if chapter_exists else ("🔒" if not is_complete else "⬜")

            with st.expander(f"{status} {label}", expanded=chapter_exists):
                if chapter_exists:
                    st.markdown(st.session_state.chapters[i])
                    if st.button("↩️ Opnieuw genereren", key=f"regen_{i}"):
                        with st.spinner(f"Hoofdstuk {i + 1} herschrijven..."):
                            st.session_state.chapters[i] = generate_chapter(client, chunk, i)
                        autosave(st.session_state.messages, st.session_state.chapters)
                        st.rerun()
                elif is_complete:
                    st.caption("Fragment afgerond — klaar om te schrijven.")
                    if st.button(f"✍️ Schrijf hoofdstuk {i + 1}", key=f"gen_{i}"):
                        with st.spinner(f"Hoofdstuk {i + 1} schrijven..."):
                            st.session_state.chapters[i] = generate_chapter(client, chunk, i)
                        autosave(st.session_state.messages, st.session_state.chapters)
                        st.rerun()
                else:
                    st.caption(f"Gesprek loopt nog — komt beschikbaar na {CHUNK_SIZE - len(chunk)} berichten.")

    st.divider()

    # Volledige autobiografie samenvoegen
    complete_chapters = [st.session_state.chapters[i] for i in sorted(st.session_state.chapters)]
    can_assemble = len(complete_chapters) >= 1

    if st.button("📖 Samenvoegen tot autobiografie", use_container_width=True,
                 disabled=not can_assemble):
        with st.spinner("Autobiografie samenvoegen..."):
            st.session_state.autobiography = assemble_autobiography(client, complete_chapters)
        path = save_autobiography(st.session_state.autobiography, st.session_state.base_name)
        autosave(st.session_state.messages, st.session_state.chapters)
        st.success(f"Opgeslagen als `{path.name}`")
        st.rerun()

    if st.session_state.autobiography:
        st.markdown("### 📜 Autobiografie")
        st.markdown(st.session_state.autobiography)
        st.download_button(
            "⬇️ Download",
            data=st.session_state.autobiography,
            file_name=f"autobiografie_{st.session_state.base_name}.txt",
            mime="text/plain",
            use_container_width=True,
        )
