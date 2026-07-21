import os, uuid, hmac, hashlib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Protocole 30J - Code API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB
mongo_uri = os.getenv("MONGO_URI", "mongodb+srv://jacques_mongo:Mongo_976@cluster0.b033so3.mongodb.net/")
client = MongoClient(mongo_uri)
db = client["protocole30j"]
codes_col = db["codes"]

# Creer index pour recherche rapide
codes_col.create_index("code", unique=True)

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "pr7-secret-2025")

class CodeCreate(BaseModel):
    code: str = None
    email: str = None
    plan: str = "standard"

@app.get("/")
def root():
    return {"status": "ok", "app": "Protocole 30J API"}

@app.get("/api/check")
def check_code(code: str):
    doc = codes_col.find_one({"code": code.upper().strip(), "active": True})
    if doc:
        return {"valid": True, "plan": doc.get("plan", "standard")}
    return {"valid": False}

@app.post("/api/webhook/make")
def webhook_make(data: dict):
    email = data.get("email") or data.get("customer_email") or f"user{uuid.uuid4().hex[:8]}@email.com"
    code = data.get("code") or f"P30J-{uuid.uuid4().hex[:6].upper()}"
    plan = data.get("plan", "standard")
    try:
        codes_col.insert_one({
            "code": code.upper(),
            "email": email,
            "plan": plan,
            "active": True,
            "created_at": datetime.utcnow(),
            "used": False
        })
        return {"status": "created", "code": code.upper(), "email": email}
    except Exception as e:
        if "duplicate key" in str(e):
            return {"status": "exists", "code": code.upper(), "email": email}
        raise HTTPException(400, str(e))

@app.get("/api/admin/codes")
def list_codes(secret: str):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(403, "Unauthorized")
    codes = list(codes_col.find({"active": True}, {"_id": 0, "code": 1, "email": 1, "plan": 1, "created_at": 1, "used": 1}))
    return {"count": len(codes), "codes": codes}
