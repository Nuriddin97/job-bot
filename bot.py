import asyncio
import os
import sqlite3
import smtplib
import requests

from email.message import EmailMessage
from bs4 import BeautifulSoup

from aiogram import Bot, Dispatcher
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# ================== НАСТРОЙКИ ==================
BOT_TOKEN = "8396092099:AAG4fH62AmUabmkaIGA8lp7ojpdzVNTRMQU"

SMTP_EMAIL = "your_email@gmail.com"
SMTP_PASSWORD = "APP_PASSWORD"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

PDF_DIR = "resumes"
DB_FILE = "database.db"

os.makedirs(PDF_DIR, exist_ok=True)

# ================== DATABASE ==================
conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    level TEXT,
    position TEXT,
    skills TEXT,
    experience TEXT,
    contacts TEXT
)
""")

conn.commit()

# ================== FSM ==================
class ResumeForm(StatesGroup):
    name = State()
    level = State()
    position = State()
    skills = State()
    experience = State()
    contacts = State()

# ================== PDF ==================
def generate_pdf(user_id, data):
    path = f"{PDF_DIR}/resume_{user_id}.pdf"
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
    styles = getSampleStyleSheet()
    styles["Normal"].fontName = "HeiseiMin-W3"

    doc = SimpleDocTemplate(path, pagesize=A4)
    el = []

    def add(t):
        el.append(Paragraph(t.replace("\n", "<br/>"), styles["Normal"]))
        el.append(Spacer(1, 10))

    add("<b>RESUME</b>")
    add(f"{data['name']} — {data['position']} ({data['level']})")
    add("<b>Skills:</b>")
    add(data["skills"])
    add("<b>Experience:</b>")
    add(data["experience"])
    add("<b>Contacts:</b>")
    add(data["contacts"])

    doc.build(el)
    return path

# ================== JOBS ==================
def get_jobs():
    url = "https://remoteok.com/remote-python-jobs"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")

    jobs = []
    for row in soup.select("tr.job"):
        title = row.select_one("h2")
        link = row.get("data-href")
        if title and link:
            jobs.append({
                "title": title.text.strip(),
                "link": "https://remoteok.com" + link
            })
        if len(jobs) == 5:
            break
    return jobs

# ================== EMAIL ==================
def send_email(to_email, subject, body, pdf_path):
    msg = EmailMessage()
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with open(pdf_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="pdf",
            filename=os.path.basename(pdf_path)
        )

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(SMTP_EMAIL, SMTP_PASSWORD)
    server.send_message(msg)
    server.quit()

# ================== BOT ==================
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    main_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧾 Создать резюме")],
            [KeyboardButton(text="🔍 Найти вакансии")]
        ],
        resize_keyboard=True
    )

    @dp.message(Command("start"))
    async def start(m: Message):
        await m.answer("👋 Добро пожаловать", reply_markup=main_kb)

    # ---- RESUME FSM ----
    @dp.message(lambda m: m.text == "🧾 Создать резюме")
    async def resume_start(m: Message, s: FSMContext):
        await s.set_state(ResumeForm.name)
        await m.answer("Как вас зовут?")

    @dp.message(ResumeForm.name)
    async def step1(m, s):
        await s.update_data(name=m.text)
        await s.set_state(ResumeForm.level)
        await m.answer("Ваш уровень? (Junior/Middle/Senior)")

    @dp.message(ResumeForm.level)
    async def step2(m, s):
        await s.update_data(level=m.text)
        await s.set_state(ResumeForm.position)
        await m.answer("Должность?")

    @dp.message(ResumeForm.position)
    async def step3(m, s):
        await s.update_data(position=m.text)
        await s.set_state(ResumeForm.skills)
        await m.answer("Навыки?")

    @dp.message(ResumeForm.skills)
    async def step4(m, s):
        await s.update_data(skills=m.text)
        await s.set_state(ResumeForm.experience)
        await m.answer("Опыт?")

    @dp.message(ResumeForm.experience)
    async def step5(m, s):
        await s.update_data(experience=m.text)
        await s.set_state(ResumeForm.contacts)
        await m.answer("Контакты (email)")

    @dp.message(ResumeForm.contacts)
    async def finish(m, s):
        data = await s.update_data(contacts=m.text)

        cur.execute(
            "REPLACE INTO users VALUES (?,?,?,?,?,?,?)",
            (m.from_user.id, *data.values())
        )
        conn.commit()

        pdf = generate_pdf(m.from_user.id, data)
        await m.answer_document(open(pdf, "rb"))
        await m.answer("✅ Резюме сохранено", reply_markup=main_kb)
        await s.clear()

    # ---- JOBS ----
    @dp.message(lambda m: m.text == "🔍 Найти вакансии")
    async def jobs(m: Message):
        jobs = get_jobs()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=j["title"], url=j["link"])]
            for j in jobs
        ])
        await m.answer("💼 Вакансии:", reply_markup=kb)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
