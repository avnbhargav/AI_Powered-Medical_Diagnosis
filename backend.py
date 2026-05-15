from fastapi import FastAPI
from pydantic import BaseModel
from groq import Groq
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()

GROQ_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY)
class ChatRequest(BaseModel):
    message: str
    history: list


def load_rag():
    docs = []

    for file in os.listdir("medical_data"):
        if file.endswith(".txt"):
            loader = TextLoader(f"medical_data/{file}", encoding="utf-8")
            docs.extend(loader.load())

    splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    split_docs = splitter.split_documents(docs)

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    return FAISS.from_documents(split_docs, embeddings)


db = None

@app.on_event("startup")
def startup_event():
    global db
    try:
        print("Loading RAG...")
        db = load_rag()
        print("RAG Loaded ✅")
    except Exception as e:
        print("RAG ERROR:", e)
@app.get("/")
def root():
    return {"message": "Backend is working"}

def clean_text(text):
    import re
    text = re.sub(r'([.,!?])([A-Za-z])', r'\1 \2', text)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

@app.post("/chat")
def chat(req: ChatRequest):

    docs = db.similarity_search(req.message, k=3)
    context = "\n".join([d.page_content for d in docs])

    system_prompt = f"""
 
    You are MedAgent, an advanced AI medical assistant. 
    Your goal is to help users identify possible medical conditions based on their symptoms.
    use this context:
    {context}
    PROTOCOL:
    1.  **Analyze Symptoms**: When the user provides symptoms, analyze them.
    2.  **Use Tools**: You have access to Google Search. ALWAYS use it to verify symptoms, check for recent outbreaks, or find up-to-date treatment guidelines.
    3.  **Ask Clarifying Questions**:

        - Ask 1–2 questions at a time ONLY.
        - NEVER say things like:
        "you repeated", "you already said", "let me rephrase"

        - ALWAYS accept the user's answer as valid input.
        - EVEN if the answer is short, unclear, or imperfect.

        - DO NOT correct the user.
        - DO NOT assume confusion.

        - If the answer is unclear:
        → Simply ask the next logical question.

        - Keep the conversation natural and forward-moving.

        Example behavior:
        User: "normal"
        Correct response:
        → Ask next question normally

        Wrong behavior (DO NOT DO):
        → "It seems you repeated..."
    4.  **Detect Emergencies**: If symptoms indicate a life-threatening emergency (e.g., heart attack, stroke, anaphylaxis), STOP questioning and warn the user immediately to seek emergency care.
    5.  **Tone**: Be professional, empathetic, and objective. Use plain language but maintain medical accuracy.
    
    When you are ready to provide a diagnosis (usually after 2-3 turns or if the user asks), simply state "I have enough information to generate your report."
  
"""
    messages = [{"role": "system", "content": system_prompt}] + req.history + [
        {"role": "user", "content": req.message}
    ]

    res = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages
    )

    reply = res.choices[0].message.content
    reply = clean_text(reply)

    return {"reply": reply}

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReportRequest(BaseModel):
    history: list

@app.post("/report")
def generate_report(req: ReportRequest):

    full_conversation = "\n".join([msg["content"] for msg in req.history])

    prompt = f"""
    Based on the following conversation, generate a medical report:

    {full_conversation}

    Include:
    - Possible condition
    - Reasoning
    - Precautions
    - Recommended doctor
    """

    res = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}]
    )

    return {"report": res.choices[0].message.content}