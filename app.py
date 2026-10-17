
import json
import os
import re
from io import BytesIO
from html import escape
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)

import streamlit as st
from dotenv import load_dotenv
from google import genai
from pypdf import PdfReader
import pymupdf
import pytesseract
from PIL import Image

_TESSERACT_EXE = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
if os.path.exists(_TESSERACT_EXE):
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_EXE


# =========================================================
# 1. CONFIGURATION
# =========================================================

load_dotenv()

st.set_page_config(
    page_title="AI Study Assistant",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

MODEL_NAME = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite",
)

# Limit the text sent to the AI to reduce token usage.
MAX_AI_TEXT = 12000
MAX_UPLOAD_TEXT = 1000000


# =========================================================
# 2. DARK THEME AND READABLE QUIZ OPTIONS
# =========================================================

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(
            135deg, #0b1220 0%, #111d30 55%, #102a35 100%
        );
        color: #f8fafc;
    }

    [data-testid="stSidebar"] {
        background: #101b2c;
    }

    h1, h2, h3, h4 {
        color: #f8fafc !important;
    }

    .stMarkdown, .stMarkdown p, .stMarkdown li,
    [data-testid="stCaptionContainer"] p {
        color: #e2e8f0;
    }

    [data-testid="stRadio"] label,
    [data-testid="stRadio"] label p,
    [data-testid="stRadio"] label span,
    [data-testid="stWidgetLabel"] p {
        color: #f8fafc !important;
        opacity: 1 !important;
    }

    .stButton > button,
    .stDownloadButton > button {
        min-height: 42px;
        border-radius: 10px;
        font-weight: 600;
    }

    .quiz-card {
        background: #101e32;
        border: 1px solid #475569;
        border-radius: 14px;
        padding: 18px;
        margin: 12px 0;
    }

    .quiz-card h4 {
        color: #67e8f9 !important;
    }

    .quiz-card p {
        color: #f8fafc !important;
        font-size: 1.05rem;
        line-height: 1.6;
    }

    .quiz-correct {
        background: #12372f;
        border: 1px solid #34d399;
        border-radius: 10px;
        padding: 14px;
        color: #d1fae5 !important;
        line-height: 1.7;
        margin: 10px 0;
    }

    .quiz-incorrect {
        background: #40212b;
        border: 1px solid #fb7185;
        border-radius: 10px;
        padding: 14px;
        color: #ffe4e6 !important;
        line-height: 1.7;
        margin: 10px 0;
    }

    .quiz-correct strong {
        color: #6ee7b7 !important;
    }

    .quiz-incorrect strong {
        color: #fda4af !important;
    }

    /* FIX: keep typed text readable in Streamlit's light chat input */
    [data-testid="stChatInput"] textarea,
    [data-testid="stChatInput"] textarea:focus,
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea {
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
        caret-color: #111827 !important;
        background-color: #f8fafc !important;
        opacity: 1 !important;
    }

    [data-testid="stChatInput"] textarea::placeholder,
    [data-testid="stTextInput"] input::placeholder,
    [data-testid="stTextArea"] textarea::placeholder {
        color: #64748b !important;
        -webkit-text-fill-color: #64748b !important;
        opacity: 1 !important;
    }

    /* Streamlit chat input wrapper and send button stay visible */
    [data-testid="stChatInput"] {
        background-color: #f8fafc !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 10px !important;
    }

    [data-testid="stChatInput"] button {
        color: #ffffff !important;
        background-color: #ef4444 !important;
    }

    div[data-baseweb="select"] * {
        color: #0f172a;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 3. GEMINI CLIENT
# =========================================================

# Streamlit Cloud uses st.secrets; local development can use a .env file.
try:
    api_key = str(st.secrets["GEMINI_API_KEY"]).strip()
except (KeyError, FileNotFoundError):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

if not api_key:
    st.error(
        "Gemini API key is not configured. Add GEMINI_API_KEY in "
        "Streamlit Cloud → App settings → Secrets, or add it to your local .env file."
    )
    st.stop()

client = genai.Client(api_key=api_key)


def ask_ai(prompt, max_output_tokens=1800):
    """Generate an answer using Gemini and show useful errors when it fails."""
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={
                "max_output_tokens": max_output_tokens,
                "temperature": 0.3,
            },
        )

        answer = response.text
        if not answer or not answer.strip():
            raise RuntimeError(
                "Gemini returned an empty answer. Please try again."
            )
        return answer.strip()

    except Exception as error:
        message = str(error).lower()
        if "503" in message or "unavailable" in message or "overloaded" in message:
            friendly = (
                "Gemini is temporarily busy. Please wait a little and try again. "
                "Your uploaded material may still be available."
            )
        elif "429" in message or "resource_exhausted" in message or "quota" in message:
            friendly = (
                "The AI service has reached a rate or usage limit. Please wait "
                "for the limit to reset, then try again."
            )
        elif "401" in message or "403" in message or "api key" in message:
            friendly = (
                "Gemini rejected the request. Check the API key and API access settings."
            )
        else:
            friendly = "The AI request failed. Please try again. Details: " + str(error)[:250]
        raise RuntimeError(friendly) from error


def save_result(title, text):
    st.session_state.last_title = title
    st.session_state.last_result = text


def limited_material(text, limit=MAX_AI_TEXT):
    """Keep prompts smaller to reduce input token usage."""
    text = (text or "").strip()
    if len(text) > limit:
        return text[:limit] + "\n[Material shortened to save tokens.]"
    return text


# =========================================================
# 4. QUIZ PARSER
# =========================================================

def parse_quiz(text):
    """Parse the JSON quiz returned by Gemini."""
    cleaned = text.strip()
    cleaned = re.sub(
        r"^```(?:json)?\s*", "", cleaned, flags=re.I
    )
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise ValueError("Quiz JSON was invalid. Generate again.")
        data = json.loads(match.group(0))

    items = data.get("questions", []) if isinstance(data, dict) else data

    if not isinstance(items, list) or not items:
        raise ValueError("No quiz questions were returned.")

    questions = []

    for item in items:
        if not isinstance(item, dict):
            continue

        question_text = str(item.get("question", "")).strip()
        raw_options = item.get("options", [])
        answer = str(
            item.get("answer", item.get("correct_answer", ""))
        ).strip().upper()
        explanation = str(item.get("explanation", "")).strip()

        if not question_text or not isinstance(raw_options, list):
            continue

        options = []

        for i, raw in enumerate(raw_options[:4]):
            letter = chr(65 + i)

            if isinstance(raw, dict):
                label = str(raw.get("label", raw.get("text", ""))).strip()
                value = str(raw.get("value", letter)).strip().upper()
            else:
                label = str(raw).strip()
                value = letter

            if label:
                options.append({"label": label, "value": value})

        if len(options) != 4:
            continue

        # Accept only a valid A/B/C/D answer.
        if answer not in {"A", "B", "C", "D"}:
            for i, option in enumerate(options):
                if answer in {
                    option["value"].upper(),
                    option["label"].upper(),
                }:
                    answer = chr(65 + i)
                    break

        if answer not in {"A", "B", "C", "D"}:
            continue

        questions.append({
            "question": question_text,
            "options": options,
            "answer": answer,
            "explanation": explanation or "Review this topic in your notes.",
        })

    if not questions:
        raise ValueError("No valid multiple-choice questions were found.")

    return questions


def correct_option_for(question):
    """Return the correct option using its A/B/C/D position."""
    index = ord(question["answer"]) - ord("A")
    if 0 <= index < len(question["options"]):
        return question["options"][index]
    return None


# =========================================================
# 4B. PROFESSIONAL PDF REPORT GENERATION
# =========================================================

def _pdf_safe(value):
    """Normalize text for reliable PDF paragraph rendering."""
    text = str(value or "")
    text = text.replace("\u00a0", " ").replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    return xml_escape(text).replace("\n", "<br/>")


def build_quiz_pdf(topic, questions, include_answers=True):
    """Create a polished printable quiz; answer key is always after all MCQs."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=19 * mm, leftMargin=19 * mm,
        topMargin=20 * mm, bottomMargin=18 * mm,
        title=f"Practice Quiz - {topic}",
        author="AI Study Assistant",
    )
    base = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "QuizTitle", parent=base["Title"], fontName="Helvetica-Bold",
        fontSize=21, leading=26, textColor=colors.HexColor("#12304A"),
        alignment=TA_CENTER, spaceAfter=7 * mm,
    )
    subtitle_style = ParagraphStyle(
        "QuizSubtitle", parent=base["Normal"], fontName="Helvetica",
        fontSize=10, leading=14, textColor=colors.HexColor("#526273"),
        alignment=TA_CENTER, spaceAfter=2 * mm,
    )
    section_style = ParagraphStyle(
        "SectionHeading", parent=base["Heading2"], fontName="Helvetica-Bold",
        fontSize=14, leading=18, textColor=colors.HexColor("#087E8B"),
        spaceBefore=4 * mm, spaceAfter=4 * mm,
    )
    question_style = ParagraphStyle(
        "QuestionText", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=10.2, leading=14, textColor=colors.HexColor("#182433"),
        spaceAfter=2 * mm,
    )
    option_style = ParagraphStyle(
        "OptionText", parent=base["Normal"], fontName="Helvetica",
        fontSize=9.6, leading=13, leftIndent=5 * mm,
        textColor=colors.HexColor("#263746"), spaceAfter=1.1 * mm,
    )
    answer_style = ParagraphStyle(
        "AnswerText", parent=base["Normal"], fontName="Helvetica",
        fontSize=9.5, leading=13, textColor=colors.HexColor("#263746"),
        spaceAfter=2 * mm,
    )
    small_style = ParagraphStyle(
        "SmallNote", parent=base["Normal"], fontSize=8.5, leading=11,
        textColor=colors.HexColor("#526273"), alignment=TA_CENTER,
    )

    story = [
        Spacer(1, 8 * mm),
        Paragraph("PRACTICE QUIZ", title_style),
        Paragraph(_pdf_safe(topic), subtitle_style),
        Paragraph(f"Total Questions: {len(questions)}  |  Type: Multiple Choice", subtitle_style),
        Spacer(1, 5 * mm),
    ]
    info = Table([[Paragraph("Student Name: __________________________________", answer_style),
                   Paragraph("Date: __________________", answer_style)]],
                 colWidths=[105 * mm, 55 * mm])
    info.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F6F9")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#C9D7E2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story += [info, Spacer(1, 6 * mm), Paragraph("SECTION A — MULTIPLE-CHOICE QUESTIONS", section_style)]
    story.append(Paragraph("Instructions: Select one best answer for each question. The answer key and explanations, if included, are placed after all questions.", answer_style))
    story.append(Spacer(1, 2 * mm))

    for index, question in enumerate(questions, start=1):
        block = [Paragraph(f"Q{index}. {_pdf_safe(question['question'])}", question_style)]
        for opt_index, option in enumerate(question["options"]):
            letter = chr(65 + opt_index)
            label = option["label"]
            # Remove a repeated A)/B)/C)/D) prefix so the PDF stays tidy.
            label = re.sub(r"^[A-Da-d][\)\.]\s*", "", label)
            block.append(Paragraph(f"{letter}. {_pdf_safe(label)}", option_style))
        block.append(Spacer(1, 3 * mm))
        story.append(KeepTogether(block))

    if include_answers:
        story.append(PageBreak())
        story.append(Paragraph("SECTION B — ANSWER KEY & EXPLANATIONS", section_style))
        story.append(Paragraph("Use this section only after completing all multiple-choice questions.", answer_style))
        story.append(Spacer(1, 2 * mm))
        for index, question in enumerate(questions, start=1):
            correct = correct_option_for(question)
            if correct:
                answer_letter = question["answer"]
                answer_text = re.sub(r"^[A-Da-d][\)\.]\s*", "", correct["label"])
            else:
                answer_letter, answer_text = question.get("answer", "?"), "Answer unavailable"
            story.append(KeepTogether([
                Paragraph(f"Q{index}. Answer: {answer_letter} — {_pdf_safe(answer_text)}", question_style),
                Paragraph(f"Explanation: {_pdf_safe(question.get('explanation', ''))}", answer_style),
                Spacer(1, 2 * mm),
            ]))

    def page_footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D7E1E8"))
        canvas.line(19 * mm, 13 * mm, A4[0] - 19 * mm, 13 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#627282"))
        canvas.drawString(19 * mm, 8 * mm, "AI Study Assistant | Practice Material")
        canvas.drawRightString(A4[0] - 19 * mm, 8 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    return buffer.getvalue()


def build_text_pdf(title, text):
    """Create a clean PDF report for notes, summaries, and chat answers."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=20*mm, bottomMargin=18*mm, title=title,
                            author="AI Study Assistant")
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                                 fontSize=18, leading=23, textColor=colors.HexColor("#12304A"),
                                 alignment=TA_CENTER, spaceAfter=8*mm)
    body_style = ParagraphStyle("ReportBody", parent=styles["BodyText"], fontName="Helvetica",
                                fontSize=10, leading=15, textColor=colors.HexColor("#263746"),
                                spaceAfter=3*mm)
    story = [Paragraph(_pdf_safe(title), title_style), Spacer(1, 2*mm)]
    for line in str(text).splitlines():
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 2*mm))
        elif stripped.startswith("### "):
            story.append(Paragraph(_pdf_safe(stripped[4:]), styles["Heading3"]))
        elif stripped.startswith("## "):
            story.append(Paragraph(_pdf_safe(stripped[3:]), styles["Heading2"]))
        elif stripped.startswith("# "):
            story.append(Paragraph(_pdf_safe(stripped[2:]), styles["Heading1"]))
        elif stripped.startswith(("- ", "* ")):
            story.append(Paragraph("&#8226; " + _pdf_safe(stripped[2:]), body_style))
        else:
            story.append(Paragraph(_pdf_safe(stripped), body_style))
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#627282"))
        canvas.drawString(20*mm, 8*mm, "AI Study Assistant")
        canvas.drawRightString(A4[0]-20*mm, 8*mm, f"Page {document.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


# =========================================================
# 5. SESSION STATE
# =========================================================

defaults = {
    "chat_history": [],
    "last_title": "",
    "last_result": "",
    "study_material": "",
    "quiz_questions": [],
    "quiz_topic": "",
    "quiz_id": 0,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# 6. HEADER AND SIDEBAR
# =========================================================

st.markdown(
    "<div style=\"text-align:center; padding:8px 0 2px; color:#94a3b8; "
    "font-size:0.95rem;\">Created by <strong style=\"color:#e2e8f0;\">"
    "Ayankhan Pathan</strong></div>",
    unsafe_allow_html=True,
)
st.title("📚 AI Study Assistant")
st.markdown("### Learn smarter. Revise faster. Understand better.")
st.caption("An AI-powered learning companion for students")

with st.sidebar:
    st.title("🎓 Study Centre")
    st.write("Choose your learning tool.")

    tool = st.radio(
        "AI Tools",
        [
            "Study Chat",
            "Notes Generator",
            "Text Summarizer",
            "Quiz Generator",
        ],
        key="selected_tool",
    )

    level = st.selectbox(
        "Explanation level",
        ["Simple", "Intermediate", "Advanced"],
    )

    st.divider()
    st.markdown("**Study Assistant features**")
    st.write("💬 Ask questions")
    st.write("📝 Generate notes")
    st.write("📄 Summarize study material")
    st.write("❓ Generate practice quizzes")
    st.write("📥 Download generated answers")

    if st.button("Clear chat history"):
        st.session_state.chat_history = []
        st.rerun()


# =========================================================
# 7. UPLOAD PDF OR TXT
# =========================================================

with st.expander("📎 Upload study material (optional)"):

    uploaded = st.file_uploader(
        "Choose a PDF or TXT file (up to 500 MB)",
        type=["pdf", "txt"],
        help="Text-based PDFs work best. Scanned PDFs may need OCR.",
        key="study_file_upload",
    )

    if uploaded is not None:
        # Avoid re-extracting the same file on every rerun.
        file_signature = (
            uploaded.name,
            uploaded.size,
        )

        if st.session_state.get("loaded_file_signature") != file_signature:
            try:
                if uploaded.name.lower().endswith(".pdf"):
                    pdf_bytes = uploaded.getvalue()
                    reader = PdfReader(BytesIO(pdf_bytes))

                    if reader.is_encrypted:
                        st.warning("This PDF is password-protected. Remove its password and upload it again.")
                        material = ""
                    else:
                        parts = []
                        char_count = 0
                        pdf_for_ocr = None
                        ocr_used = False

                        # Extract embedded text first. If a page has no meaningful
                        # text, render that page and use Tesseract OCR.
                        try:
                            pdf_for_ocr = pymupdf.open(stream=pdf_bytes, filetype="pdf")
                        except Exception as render_error:
                            st.warning(f"Could not prepare PDF pages for OCR: {render_error}")

                        total_pages = len(reader.pages)
                        progress = st.progress(0, text="Reading PDF text…")
                        for page_index, page in enumerate(reader.pages):
                            if char_count >= MAX_UPLOAD_TEXT:
                                break

                            page_text = (page.extract_text() or "").strip()

                            # OCR pages that have no/little extracted text, including
                            # scanned PDFs that contain only page images.
                            if len(page_text) < 40 and pdf_for_ocr is not None:
                                try:
                                    pix = pdf_for_ocr[page_index].get_pixmap(
                                        matrix=pymupdf.Matrix(2, 2),
                                        alpha=False,
                                    )
                                    image = Image.open(BytesIO(pix.tobytes("png")))
                                    ocr_text = pytesseract.image_to_string(
                                        image, lang="eng"
                                    ).strip()
                                    if len(ocr_text) > len(page_text):
                                        page_text = ocr_text
                                        ocr_used = True
                                except Exception as ocr_error:
                                    st.warning(
                                        f"OCR could not read page {page_index + 1}: "
                                        f"{ocr_error}"
                                    )

                            remaining = MAX_UPLOAD_TEXT - char_count
                            page_text = page_text[:remaining]
                            if page_text:
                                parts.append(page_text)
                                char_count += len(page_text)

                            progress.progress(
                                min((page_index + 1) / max(total_pages, 1), 1.0),
                                text=f"Reading page {page_index + 1} of {total_pages}…",
                            )

                        progress.empty()
                        if pdf_for_ocr is not None:
                            pdf_for_ocr.close()

                        material = "\\n\\n".join(parts).strip()
                        if ocr_used and material:
                            st.info("OCR was used to read scanned or image-based PDF pages.")
                else:
                    material = uploaded.getvalue().decode(
                        "utf-8-sig", errors="replace"
                    ).strip()[:MAX_UPLOAD_TEXT]

                if material:
                    st.session_state.study_material = material
                    st.session_state.loaded_file_signature = file_signature
                    st.success(
                        f"Text extracted: {len(material):,} characters."
                    )

                    if len(material) >= MAX_UPLOAD_TEXT:
                        st.warning(
                            "Only the first 1,000,000 characters were extracted."
                        )
                else:
                    st.warning(
                        "No readable text was found in this file."
                    )

            except Exception as error:
                st.error(f"Could not read the file: {error}")

    if st.session_state.study_material:
        st.caption(
            f"Loaded study text: "
            f"{len(st.session_state.study_material):,} characters"
        )

        if st.button("Remove uploaded material"):
            st.session_state.study_material = ""
            st.session_state.loaded_file_signature = None
            st.rerun()


# =========================================================
# 8. STUDY CHAT
# =========================================================

if tool == "Study Chat":
    st.subheader("💬 AI Study Chat")
    st.write("Ask questions about any subject or uploaded material.")

    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Ask a study question...")

    if question:
        st.session_state.chat_history.append({
            "role": "user",
            "content": question,
        })

        recent = st.session_state.chat_history[-7:-1]
        history = "\n".join(
            f"{m['role']}: {m['content']}" for m in recent
        )

        prompt = f"""
You are a helpful multi-subject study assistant.
Answer the student's actual question, not a default AI topic.
Use {level.lower()} language. Be accurate and concise.
Use examples or bullets when useful. State uncertainty honestly.

Study material:
{limited_material(st.session_state.study_material, 7000)}

Recent chat:
{history}

Student question:
{question}
"""

        with st.spinner("Preparing your answer..."):
            try:
                answer = ask_ai(prompt, 1500)
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": answer,
                })
                save_result("Study Chat Answer", answer)
                st.rerun()
            except Exception as error:
                st.error(f"Could not generate answer: {error}")


# =========================================================
# 9. NOTES GENERATOR
# =========================================================

elif tool == "Notes Generator":
    st.subheader("📝 Notes Generator")

    topic = st.text_input(
        "Enter any subject or topic",
        placeholder="Example: Supply Chain Management",
    )

    style = st.selectbox(
        "Notes format",
        [
            "Headings and bullet points",
            "Exam preparation notes",
            "Short revision notes",
            "Detailed notes with examples",
        ],
    )

    if st.button("Generate Notes", type="primary"):
        if not topic.strip() and not st.session_state.study_material:
            st.warning("Enter a topic or upload study material.")
        else:
            prompt = f"""
Create {style.lower()} for the requested topic.
Topic: {topic or "Uploaded study material"}
Difficulty: {level}

Stay on the requested subject. Use clear headings and concise bullets.
Include definitions and examples only when relevant.
Do not invent facts.

Study material:
{limited_material(st.session_state.study_material, 9000)}
"""
            with st.spinner("Generating notes..."):
                try:
                    result = ask_ai(prompt, 2200)
                    save_result("Study Notes", result)
                    st.markdown(result)
                except Exception as error:
                    st.error(f"Could not generate notes: {error}")


# =========================================================
# 10. TEXT SUMMARIZER
# =========================================================

elif tool == "Text Summarizer":
    st.subheader("📄 Text Summarizer")

    source_text = st.text_area(
        "Paste study material or use the uploaded text",
        value=st.session_state.study_material,
        height=220,
        placeholder="Paste text here...",
    )

    style = st.selectbox(
        "Summary style",
        [
            "Short summary",
            "Detailed summary",
            "Key points for revision",
            "Exam-oriented summary",
        ],
    )

    if st.button("Summarize Text", type="primary"):
        if not source_text.strip():
            st.warning("Paste text or upload study material.")
        else:
            prompt = f"""
Summarize this material in {level.lower()} language.
Style: {style}
Preserve the original subject, key terms and important facts.
Do not add unsupported information. Be concise.

Material:
{limited_material(source_text, 12000)}
"""
            with st.spinner("Summarizing..."):
                try:
                    result = ask_ai(prompt, 1800)
                    save_result("Study Summary", result)
                    st.markdown(result)
                except Exception as error:
                    st.error(f"Could not summarize text: {error}")


# =========================================================
# 11. QUIZ GENERATOR - 30 TO 35 MCQS
# =========================================================

elif tool == "Quiz Generator":
    st.subheader("❓ Quiz Generator")
    st.write(
        "Generate a quiz for any subject. Select an option to reveal "
        "the correct answer and explanation."
    )

    topic = st.text_input(
        "Enter the quiz subject or topic",
        placeholder="Example: Commerce or Supply Chain Management",
    )

    question_count = st.slider(
        "Number of questions",
        min_value=30,
        max_value=35,
        value=30,
        step=1,
    )

    if st.button("Generate Quiz", type="primary"):
        if not topic.strip() and not st.session_state.study_material:
            st.warning("Enter a topic or upload study material.")
        else:
            requested_topic = topic.strip() or "the uploaded study material"
            material = limited_material(
                st.session_state.study_material, 24000
            )

            prompt = f"""
Create {question_count} multiple-choice questions for this topic:
"{requested_topic}"

CRITICAL: Stay on the requested subject.
Do not default to Artificial Intelligence.
For example, Commerce means commerce; Supply Chain Management means
procurement, inventory, logistics, suppliers and distribution.
If study material is uploaded, use ONLY its relevant content as the primary source. Avoid questions about topics not covered in the uploaded chapter.
If no material is uploaded, use your knowledge of the requested topic.

Difficulty: {level}

Requirements:
- Exactly {question_count} questions.
- Four options per question, labelled A), B), C), D).
- One correct answer per question.
- "answer" must be only A, B, C or D.
- Give a short explanation (one sentence).
- Avoid duplicate questions and unrelated topics.
- Keep wording and explanations concise to reduce output tokens.
- Return ONLY valid JSON. No Markdown or extra text.

Required format:
{{
  "questions": [
    {{
      "question": "Question text",
      "options": [
        {{"label": "A) Option one", "value": "A"}},
        {{"label": "B) Option two", "value": "B"}},
        {{"label": "C) Option three", "value": "C"}},
        {{"label": "D) Option four", "value": "D"}}
      ],
      "answer": "B",
      "explanation": "Short reason."
    }}
  ]
}}

Uploaded study material:
{material or "No uploaded material."}
"""

            # 30-35 questions need more output tokens than a short answer.
            # This cap reduces runaway responses but must allow quiz JSON.
            output_limit = 7000 if question_count <= 32 else 8000

            with st.spinner(
                f"Generating {question_count} questions. This may take a moment..."
            ):
                try:
                    raw = ask_ai(prompt, output_limit)
                    questions = parse_quiz(raw)

                    if len(questions) < question_count:
                        st.warning(
                            f"The model returned {len(questions)} valid questions "
                            f"instead of {question_count}. You can generate again."
                        )

                    st.session_state.quiz_questions = questions
                    st.session_state.quiz_topic = requested_topic
                    st.session_state.quiz_id += 1

                    save_result("Practice Quiz", raw)
                    st.rerun()

                except Exception as error:
                    st.error(f"Could not generate quiz: {error}")
                    st.caption(
                        "If this is a 503 error, the model may be busy. "
                        "If output is truncated, try 30 questions."
                    )

    if st.session_state.quiz_questions:
        questions = st.session_state.quiz_questions

        st.markdown(
            f"### Multiple-Choice Quiz: {st.session_state.quiz_topic}"
        )
        st.info(
            "Choose an answer for each question. The answer and explanation "
            "appear only after you select an option."
        )

        correct_count = 0
        answered_count = 0

        for index, question in enumerate(questions):
            st.markdown(
                f"""
                <div class="quiz-card">
                    <h4>Question {index + 1}</h4>
                    <p>{escape(question["question"])}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            labels = [option["label"] for option in question["options"]]
            key = f"quiz_{st.session_state.quiz_id}_{index}"

            selected = st.radio(
                f"Choose an answer for question {index + 1}",
                options=labels,
                index=None,
                key=key,
                label_visibility="collapsed",
            )

            # No answer or explanation is displayed until selection.
            if selected is None:
                st.caption("Select an option to check your answer.")
            else:
                answered_count += 1
                correct = correct_option_for(question)

                if correct is None:
                    st.warning("Could not identify the correct option.")
                elif selected == correct["label"]:
                    correct_count += 1
                    st.markdown(
                        f"""
                        <div class="quiz-correct">
                            <strong>✅ Correct!</strong><br>
                            <strong>Answer:</strong> {escape(correct["label"])}<br>
                            <strong>Explanation:</strong>
                            {escape(question["explanation"])}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"""
                        <div class="quiz-incorrect">
                            <strong>❌ Incorrect.</strong><br>
                            <strong>Your answer:</strong> {escape(selected)}<br>
                            <strong>Correct answer:</strong>
                            {escape(correct["label"])}<br>
                            <strong>Explanation:</strong>
                            {escape(question["explanation"])}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            st.divider()

        st.markdown(
            f"**Progress:** {answered_count}/{len(questions)} answered "
            f" · **Correct answers:** {correct_count}"
        )

        st.divider()
        st.subheader("📄 Download Professional Quiz PDF")
        st.caption("The PDF lists every MCQ first. The answer key and explanations begin on a separate page after the final question.")
        safe_topic = re.sub(r"[^A-Za-z0-9_-]+", "_", st.session_state.quiz_topic).strip("_") or "Quiz"
        try:
            combined_pdf = build_quiz_pdf(st.session_state.quiz_topic, questions, include_answers=True)
            questions_pdf = build_quiz_pdf(st.session_state.quiz_topic, questions, include_answers=False)
            pdf_col1, pdf_col2 = st.columns(2)
            with pdf_col1:
                st.download_button(
                    "⬇️ Download Quiz + Answer Key (PDF)",
                    data=combined_pdf,
                    file_name=f"{safe_topic}_Quiz_With_Answer_Key.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"quiz_pdf_all_{st.session_state.quiz_id}",
                )
            with pdf_col2:
                st.download_button(
                    "⬇️ Download Questions Only (PDF)",
                    data=questions_pdf,
                    file_name=f"{safe_topic}_Questions_Only.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"quiz_pdf_questions_{st.session_state.quiz_id}",
                )
        except Exception as error:
            st.error(f"Could not prepare the quiz PDF: {error}")

        if st.button("Clear this quiz"):

            st.session_state.quiz_questions = []
            st.session_state.quiz_topic = ""
            st.rerun()


# =========================================================
# 12. DOWNLOAD GENERATED ANSWERS
# =========================================================

if st.session_state.last_result:
    st.divider()
    st.subheader("📥 Download Your Study Material")

    download_col1, download_col2 = st.columns(2)
    with download_col1:
        st.download_button(
            "⬇️ Download as TXT",
            data=(st.session_state.last_title + "\n\n" + st.session_state.last_result),
            file_name="study_material.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with download_col2:
        try:
            report_pdf = build_text_pdf(st.session_state.last_title, st.session_state.last_result)
            st.download_button(
                "⬇️ Download Report as PDF",
                data=report_pdf,
                file_name="study_material_report.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as error:
            st.warning(f"PDF report could not be created: {error}")

    with st.expander("View latest generated result"):
        st.markdown(st.session_state.last_result)


# =========================================================
# 13. FOOTER
# =========================================================

st.divider()
st.caption(
    "AI Study Assistant | Check important answers against textbooks "
    "and trusted sources."
)
st.markdown(
    "<div style=\"text-align:center; padding:10px 0 4px; color:#94a3b8; "
    "font-size:0.9rem;\">Created by <strong style=\"color:#e2e8f0;\">Ayankhan Pathan</strong></div>",
    unsafe_allow_html=True,
)
