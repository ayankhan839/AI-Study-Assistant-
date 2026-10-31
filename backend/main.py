import json
import os
import re
from io import BytesIO
from pathlib import Path
from typing import Literal

import fitz
import pytesseract
from docx import Document
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google import genai
from google.genai import types
from PIL import Image, ImageEnhance, ImageOps
from pydantic import BaseModel, Field
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_UPLOAD_TEXT = 1000000
MAX_AI_TEXT = 12000
api_key = os.getenv("GEMINI_API_KEY", "").strip()
client = genai.Client(api_key=api_key) if api_key else None

app = FastAPI(title="AI Study Assistant API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])

class StudyRequest(BaseModel):
    material: str = Field(default="", max_length=MAX_UPLOAD_TEXT)
    question: str = Field(default="", max_length=5000)
    topic: str = Field(default="", max_length=500)
    level: Literal["Simple", "Intermediate", "Advanced"] = "Simple"
    style: str = Field(default="", max_length=100)
    count: int = Field(default=30, ge=30, le=35)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)

def ask_ai(prompt, max_output_tokens=1800):
    if client is None:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured on the backend.")
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt, config={"max_output_tokens": max_output_tokens, "temperature": 0.3})
        answer = (response.text or "").strip()
        if not answer:
            raise RuntimeError("Gemini returned an empty answer.")
        return answer
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "503" in message or "unavailable" in message:
            detail = "Gemini is temporarily busy. Try again shortly."
        elif "429" in message or "quota" in message:
            detail = "Gemini usage limit reached. Try again later."
        else:
            detail = "AI request failed: " + str(exc)[:200]
        raise HTTPException(status_code=502, detail=detail) from exc

def limited_material(text, limit=MAX_AI_TEXT):
    text = (text or "").strip()
    return text[:limit] + ("\n[Material shortened to save tokens.]" if len(text) > limit else "")

def extract_docx(data):
    doc = Document(BytesIO(data))
    parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)[:MAX_UPLOAD_TEXT]

def extract_pdf(data):
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("PDF is password-protected.")
    try:
        rendered = fitz.open(stream=data, filetype="pdf")
    except Exception:
        rendered = None
    try:
        langs = set(pytesseract.get_languages(config="")) if rendered else set()
    except Exception:
        langs = set()
    selected = [x for x in ["eng", "guj", "hin"] if x in langs]
    language = "+".join(selected) or "eng"
    parts, ocr_pages, failed = [], [], []
    total = 0
    for i, page in enumerate(reader.pages):
        if total >= MAX_UPLOAD_TEXT:
            break
        text = (page.extract_text() or "").strip()
        if len(text) < 40 and rendered:
            try:
                pix = rendered[i].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False, colorspace=fitz.csGRAY)
                image = ImageOps.autocontrast(Image.open(BytesIO(pix.tobytes("png"))).convert("L"))
                image = ImageEnhance.Contrast(image).enhance(1.25)
                ocr = pytesseract.image_to_string(image, lang=language, config="--psm 3").strip()
                if len(ocr) > len(text):
                    text = ocr
                    ocr_pages.append(i + 1)
            except Exception:
                failed.append(i + 1)
        text = text[:MAX_UPLOAD_TEXT-total]
        if text:
            parts.append(text)
            total += len(text)
    if rendered:
        rendered.close()
    return {"text": "\n\n".join(parts).strip(), "pages": len(reader.pages), "ocr_pages": ocr_pages, "failed_ocr_pages": failed, "ocr_languages": selected}

def extract_image(data):
    image = ImageOps.exif_transpose(Image.open(BytesIO(data))).convert("RGB")
    gray = ImageEnhance.Contrast(ImageOps.autocontrast(image.convert("L"))).enhance(1.25)
    try:
        langs = set(pytesseract.get_languages(config=""))
    except Exception:
        langs = set()
    selected = [x for x in ["eng", "guj", "hin"] if x in langs]
    local = pytesseract.image_to_string(gray, lang="+".join(selected) or "eng", config="--psm 3").strip()
    return {"text": local[:MAX_UPLOAD_TEXT], "ocr_languages": selected}

@app.get("/api/health")
def health():
    return {"status": "ok", "gemini_configured": client is not None, "model": MODEL_NAME}

@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    name = file.filename or "upload"
    ext = Path(name).suffix.lower()
    allowed = [".pdf", ".txt", ".docx", ".jpg", ".jpeg", ".jfif", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"]
    if ext not in allowed:
        raise HTTPException(status_code=415, detail="Unsupported file type.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File is empty.")
    try:
        if ext == ".pdf":
            result = extract_pdf(data)
        elif ext == ".docx":
            result = {"text": extract_docx(data)}
        elif ext in [".jpg", ".jpeg", ".jfif", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"]:
            result = extract_image(data)
        else:
            result = {"text": data.decode("utf-8-sig", errors="replace")[:MAX_UPLOAD_TEXT]}
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Could not read file: " + str(exc)[:200]) from exc
    if not result.get("text"):
        raise HTTPException(status_code=422, detail="No readable text was found.")
    return {"filename": name, "characters": len(result["text"]), **result}

@app.post("/api/chat")
def chat(req: StudyRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Enter a question.")
    history = "\n".join(f"{m.get('role')}: {m.get('content', '')[:2000]}" for m in req.history[-6:])
    prompt = f"""You are a helpful multi-subject study assistant. Answer the student's actual question.
Use {req.level.lower()} language. Be accurate and concise. Use examples or bullets when useful.
Treat uploaded material as the primary source. If it does not contain the answer, say so.
Study material:
{limited_material(req.material, 7000)}
Recent chat:
{history}
Student question:
{req.question}"""
    return {"answer": ask_ai(prompt, 1500)}

@app.post("/api/notes")
def notes(req: StudyRequest):
    if not req.topic.strip() and not req.material.strip():
        raise HTTPException(status_code=400, detail="Enter a topic or upload study material.")
    prompt = f"""Create {(req.style or 'Headings and bullet points').lower()} for this topic.
Topic: {req.topic or 'Uploaded study material'}
Difficulty: {req.level}
Use clear headings and concise bullets. Include definitions and examples only when relevant.
Use uploaded material as primary source. Do not invent source-specific facts.
Study material:
{limited_material(req.material, 9000)}"""
    return {"title": "Study Notes", "result": ask_ai(prompt, 2200)}

@app.post("/api/summarize")
def summarize(req: StudyRequest):
    if not req.material.strip():
        raise HTTPException(status_code=400, detail="Paste or upload study material.")
    prompt = f"""Summarize in {req.level.lower()} language.
Style: {req.style or 'Short summary'}
Preserve the source subject, key terms and facts. Do not add unsupported information.
Material:
{limited_material(req.material, MAX_AI_TEXT)}"""
    return {"title": "Study Summary", "result": ask_ai(prompt, 1800)}

def parse_quiz(raw):
    cleaned = re.sub(r"^\x60{3}(?:json)?\s*", "", raw.strip(), flags=re.I)
    cleaned = re.sub(r"\s*\x60{3}$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise ValueError("Quiz JSON was invalid.")
        data = json.loads(match.group(0))
    items = data.get("questions", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("No quiz questions were returned.")
    questions = []
    for item in items:
        if not isinstance(item, dict):
            continue
        q = str(item.get("question", "")).strip()
        raw_options = item.get("options", [])
        answer = str(item.get("answer", item.get("correct_answer", ""))).strip().upper()
        if not q or not isinstance(raw_options, list):
            continue
        options = []
        for i, opt in enumerate(raw_options[:4]):
            letter = chr(65+i)
            label = str(opt.get("label", opt.get("text", ""))).strip() if isinstance(opt, dict) else str(opt).strip()
            value = str(opt.get("value", letter)).upper() if isinstance(opt, dict) else letter
            if label:
                options.append({"label": label, "value": value})
        if len(options) != 4:
            continue
        if answer not in ["A", "B", "C", "D"]:
            for i, opt in enumerate(options):
                if answer in [opt["value"], opt["label"].upper()]:
                    answer = chr(65+i)
                    break
        if answer not in ["A", "B", "C", "D"]:
            continue
        questions.append({"question": q, "options": options, "answer": answer, "explanation": str(item.get("explanation", "")).strip() or "Review this topic in your notes."})
    if not questions:
        raise ValueError("No valid multiple-choice questions were found.")
    return questions

@app.post("/api/quiz")
def quiz(req: StudyRequest):
    if not req.topic.strip() and not req.material.strip():
        raise HTTPException(status_code=400, detail="Enter a topic or upload study material.")
    topic = req.topic.strip() or "the uploaded study material"
    source = limited_material(req.material, 24000) or "No uploaded material."
    questions = []
    seen = set()
    batch_size = 8
    try:
        # Generate small batches so the model does not truncate a 30–35 question response.
        for start in range(0, req.count, batch_size):
            target = min(batch_size, req.count - start)
            attempts = 0
            while sum(1 for q in questions if q.get("_batch") == start) < target and attempts < 3:
                attempts += 1
                existing = [q["question"] for q in questions]
                remaining = target - sum(1 for q in questions if q.get("_batch") == start)
                prompt = f"""Create exactly {remaining} NEW multiple-choice questions about "{topic}".
Difficulty: {req.level}. Stay on the requested subject. Use the uploaded material as the primary source; do not invent source-specific facts.
Do not repeat or paraphrase these existing questions: {json.dumps(existing[-req.count:], ensure_ascii=False)}
Each question must have four options labelled A, B, C, D; answer must be exactly one letter A/B/C/D; include a concise explanation.
Return ONLY valid JSON in this format:
{{"questions":[{{"question":"Question text","options":[{{"label":"A) option","value":"A"}},{{"label":"B) option","value":"B"}},{{"label":"C) option","value":"C"}},{{"label":"D) option","value":"D"}}],"answer":"B","explanation":"Reason"}}]}}
Uploaded study material:
{source}"""
                batch = parse_quiz(ask_ai(prompt, 3000))
                for item in batch:
                    key = re.sub(r"\W+", " ", item["question"].lower()).strip()
                    if key in seen:
                        continue
                    seen.add(key)
                    item["_batch"] = start
                    questions.append(item)
        if len(questions) < req.count:
            raise ValueError(f"Gemini returned {len(questions)} of {req.count} requested questions. Please try again.")
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    for item in questions:
        item.pop("_batch", None)
    return {"topic": topic, "questions": questions[:req.count], "requested_count": req.count, "returned_count": min(len(questions), req.count)}

@app.post("/api/quiz/pdf")
def quiz_pdf(payload: dict):
    topic = str(payload.get("topic", "Practice Quiz"))[:500]
    questions = payload.get("questions", [])
    include_answers = bool(payload.get("include_answers", True))
    if not isinstance(questions, list) or not questions:
        raise HTTPException(status_code=400, detail="No quiz questions supplied.")
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=19*mm, leftMargin=19*mm, topMargin=20*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("QuizTitle", parent=styles["Title"], fontSize=20, textColor=colors.HexColor("#12304A"), alignment=1, spaceAfter=7*mm)
    qstyle = ParagraphStyle("Question", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=10, leading=14, spaceAfter=2*mm)
    body = ParagraphStyle("Option", parent=styles["BodyText"], fontSize=9.5, leading=13, leftIndent=5*mm, spaceAfter=1*mm)
    from xml.sax.saxutils import escape
    safe = lambda value: escape(str(value or "")).replace("\n", "<br/>")
    story = [Spacer(1, 8*mm), Paragraph("PRACTICE QUIZ", title), Paragraph(safe(topic), styles["Heading2"]), Paragraph("SECTION A — MULTIPLE-CHOICE QUESTIONS", styles["Heading2"])]
    for n, q in enumerate(questions, 1):
        block = [Paragraph(f"Q{n}. {safe(q['question'])}", qstyle)]
        for i, option in enumerate(q["options"]):
            label = re.sub(r"^[A-Da-d][\)\.]\s*", "", option["label"])
            block.append(Paragraph(f"{chr(65+i)}. {safe(label)}", body))
        story.append(KeepTogether(block))
        story.append(Spacer(1, 3*mm))
    if include_answers:
        story.extend([PageBreak(), Paragraph("SECTION B — ANSWER KEY & EXPLANATIONS", styles["Heading2"])])
        for n, q in enumerate(questions, 1):
            option = q["options"][ord(q["answer"])-65]
            story.append(KeepTogether([Paragraph(f"Q{n}. Answer: {q['answer']} — {safe(option['label'])}", qstyle), Paragraph("Explanation: " + safe(q.get("explanation", "")), body)]))
    doc.build(story)
    suffix = "With_Answer_Key" if include_answers else "Questions_Only"
    filename = re.sub(r"[^A-Za-z0-9_-]+", "_", topic).strip("_") or "Quiz"
    return StreamingResponse(BytesIO(buffer.getvalue()), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}_{suffix}.pdf"'})
