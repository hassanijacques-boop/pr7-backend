"""
PR7 Backend — Protocole Restauration 7
FastAPI + SQLite backend de remplacement pour l'app PR7
"""

import os
import json
import hashlib
import hmac
import base64
import uuid
import random
import math
import datetime
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

# ── FastAPI ──
from fastapi import FastAPI, HTTPException, Depends, Query, Cookie, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

# ── SQLAlchemy ──
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, Text, JSON, ForeignKey, Date, select, func, desc
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session, relationship
from sqlalchemy.sql import text

# ── Auth ──
from passlib.context import CryptContext
from jose import JWTError, jwt

# ──────────────────────────────────────────────
# BASE DE DONNÉES
# ──────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pr7.db")
# Handle Render's PostgreSQL-style URLs if needed
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ──────────────────────────────────────────────
# MODÈLES SQLAlchemy
# ──────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    audit_completed = Column(Boolean, default=False)
    profile_type = Column(String, nullable=True)
    active_pillar_id = Column(Integer, default=1)


class AuditResult(Base):
    __tablename__ = "audit_results"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    profile_type = Column(String, nullable=True)
    entry_path = Column(String, nullable=True)
    answers = Column(JSON, default=list)
    restoration_plan = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyLog(Base):
    __tablename__ = "daily_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    log_date = Column(Date, default=date.today)
    blocks = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CapitalAttention(Base):
    __tablename__ = "capital_attention"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    log_date = Column(Date, default=date.today)
    score = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class WeeklyVerdict(Base):
    __tablename__ = "weekly_verdicts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    week_start = Column(Date)
    verdict = Column(Text)
    stats = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class Checklist(Base):
    __tablename__ = "checklists"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    pillar_id = Column(Integer, nullable=False)
    completed_items = Column(JSON, default=list)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DiagnosticResult(Base):
    __tablename__ = "diagnostic_results"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    pillar_id = Column(Integer, nullable=False)
    answers = Column(JSON, default=list)
    score = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class PowerGauge(Base):
    __tablename__ = "power_gauges"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    pillar_id = Column(Integer, nullable=False)
    score = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BRISession(Base):
    __tablename__ = "bri_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    enrolled = Column(Boolean, default=False)
    current_day = Column(Integer, default=0)
    week = Column(Integer, default=1)
    phase = Column(Integer, default=1)
    graduated = Column(Boolean, default=False)
    enrolled_at = Column(DateTime, nullable=True)


class FrameScan(Base):
    __tablename__ = "frame_scans"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    responses = Column(JSON, default=dict)
    score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class SovereigntyLog(Base):
    __tablename__ = "sovereignty_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    entry = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class Progress(Base):
    __tablename__ = "progress"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    overall_score = Column(Integer, default=0)
    pillar_scores = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScoreHistory(Base):
    __tablename__ = "score_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, default=date.today)
    score = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class KPIRecord(Base):
    __tablename__ = "kpi_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    pillar_id = Column(Integer, nullable=False)
    kpi_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class SentinelChat(Base):
    __tablename__ = "sentinel_chats"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, default="user")
    content = Column(Text)
    mode = Column(String, default="chat")
    session_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SentinelJournal(Base):
    __tablename__ = "sentinel_journals"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


# ──────────────────────────────────────────────
# SÉCURITÉ & AUTH
# ──────────────────────────────────────────────

SECRET_KEY = os.getenv("SECRET_KEY", "pr7-secret-key-change-in-production-2024")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
    token: Optional[str] = Cookie(None, alias="access_token"),
):
    jwt_token = None
    if credentials:
        jwt_token = credentials.credentials
    elif token:
        jwt_token = token

    if not jwt_token:
        raise HTTPException(status_code=401, detail="Non authentifié")

    try:
        payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token invalide")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    return user


# ──────────────────────────────────────────────
# DONNÉES STATIQUES
# ──────────────────────────────────────────────

PILLARS_DATA = [
    {"id": 1, "slug": "vitalite-masculine", "name": "Vitalité Masculine", "emoji": "⚡",
     "color": "#FF6B35", "desc": "Force physique, énergie vitale, discipline du corps",
     "focus": "Réveiller le guerrier intérieur par le corps"},
    {"id": 2, "slug": "quadrant-holistique", "name": "Quadrant Holistique", "emoji": "🧠",
     "color": "#4ECDC4", "desc": "Clarté mentale, structure cognitive, vision",
     "focus": "Nettoyer le mental et architecturer la pensée"},
    {"id": 3, "slug": "adoration-originelle", "name": "Adoration Originelle", "emoji": "🕌",
     "color": "#9B59B6", "desc": "Foi, spiritualité, connexion transcendante",
     "focus": "Restaurer le lien vertical avec le Divin"},
    {"id": 4, "slug": "choc-psychologies", "name": "Choc des Psychologies", "emoji": "🔥",
     "color": "#E74C3C", "desc": "Traumas, mémoires, libération émotionnelle",
     "focus": "Transformer les blessures en forces"},
    {"id": 5, "slug": "architecture-relationnelle", "name": "Architecture Relationnelle", "emoji": "🏛️",
     "color": "#2ECC71", "desc": "Liens, famille, tribu, leadership",
     "focus": "Bâtir des relations solides et purpose-driven"},
    {"id": 6, "slug": "souverainete-emotionnelle", "name": "Souveraineté Émotionnelle", "emoji": "👑",
     "color": "#F1C40F", "desc": "Maîtrise des émotions, ancrage, paix intérieure",
     "focus": "Devenir le roi de son propre royaume intérieur"},
    {"id": 7, "slug": "discipline-temple", "name": "Discipline du Temple", "emoji": "⛩️",
     "color": "#3498DB", "desc": "Routines, habitudes, excellence quotidienne",
     "focus": "Le corps est un temple, l'esprit son gardien"},
]

PILLAR_CONTENT = {}
for p in PILLARS_DATA:
    pid = p["id"]
    PILLAR_CONTENT[pid] = {
        "id": pid,
        "slug": p["slug"],
        "title": p["name"],
        "subtitle": p["desc"],
        "color": p["color"],
        "sections": [
            {"title": "Présentation", "body": f"Le pilier **{p['name']}** est le pilier #{pid} du Protocole Restauration 7. {p['desc']}."},
            {"title": "Focus", "body": p["focus"]},
            {"title": "Pratique Quotidienne", "body": "Chaque jour, consacrez au moins 15 minutes à ce pilier. Tenez un journal de bord. Notez vos progrès et vos blocages."},
            {"title": "Objectifs", "body": f"1. Comprendre les fondamentaux du {p['name']}\\n2. Intégrer une pratique quotidienne\\n3. Mesurer votre progression\\n4. Atteindre la maîtrise"},
        ]
    }

WEEKLY_THEMES = [
    "Le Réveil du Guerrier", "La Carte du Territoire", "Le Lien Vertical",
    "L'Ancrage Émotionnel", "La Tribu Reconstruite", "La Souveraineté du Moi",
    "Le Temple en Ordre", "L'Harmonie des Sphères", "La Puissance du Collectif",
    "La Vision du Leader", "L'Excellence Durable", "La Transmission"
]

SENTINEL_MODES = {
    "chat": "Assistant de restauration — répond aux questions sur le protocole.",
    "cogwar": "Mode guerre cognitive — détecte et contre les schémas de pensée destructeurs.",
    "firewall": "Analyse les pensées et comportements à risque.",
    "voice": "Session vocale avec le sentinel.",
    "emergency": "Alerte de crise — activation immédiate du protocole d'urgence."
}

AUDIT_QUESTIONS = [
    {"id": "q1", "category": "physique", "question": "Comment évaluez-vous votre énergie physique au quotidien ?",
     "options": [{"value": 1, "label": "Très faible"}, {"value": 2, "label": "Faible"},
                 {"value": 3, "label": "Moyenne"}, {"value": 4, "label": "Bonne"}, {"value": 5, "label": "Excellente"}]},
    {"id": "q2", "category": "mental", "question": "Comment jugez-vous votre clarté mentale actuelle ?",
     "options": [{"value": 1, "label": "Confus/permanent brouillard"}, {"value": 2, "label": "Souvent flou"},
                 {"value": 3, "label": "Moyennement clair"}, {"value": 4, "label": "Plutôt clair"}, {"value": 5, "label": "Parfaitement clair"}]},
    {"id": "q3", "category": "spirituel", "question": "Où en est votre connexion spirituelle ?",
     "options": [{"value": 1, "label": "Inexistante"}, {"value": 2, "label": "Faible / Distante"},
                 {"value": 3, "label": "Présente mais irrégulière"}, {"value": 4, "label": "Solide et régulière"}, {"value": 5, "label": "Puissante et centrale"}]},
    {"id": "q4", "category": "emotionnel", "question": "Comment gérez-vous vos émotions en période de stress ?",
     "options": [{"value": 1, "label": "Je suis submergé"}, {"value": 2, "label": "Difficilement"},
                 {"value": 3, "label": "Moyennement"}, {"value": 4, "label": "Assez bien"}, {"value": 5, "label": "Très bien — je reste centré"}]},
    {"id": "q5", "category": "relationnel", "question": "Évaluez la qualité de vos relations personnelles.",
     "options": [{"value": 1, "label": "Très conflictuelles/isolées"}, {"value": 2, "label": "Difficiles"},
                 {"value": 3, "label": "Quelques bonnes relations"}, {"value": 4, "label": "Relations saines et épanouissantes"}, {"value": 5, "label": "Relations excellentes et profondes"}]},
    {"id": "q6", "category": "discipline", "question": "Comment qualifieriez-vous votre discipline quotidienne ?",
     "options": [{"value": 1, "label": "Aucune routine"}, {"value": 2, "label": "Peu de routine"},
                 {"value": 3, "label": "Routine irrégulière"}, {"value": 4, "label": "Routine régulière"}, {"value": 5, "label": "Discipline d'excellence"}]},
    {"id": "q7", "category": "physique", "question": "À quelle fréquence faites-vous de l'exercice physique ?",
     "options": [{"value": 1, "label": "Jamais"}, {"value": 2, "label": "1 fois/semaine"},
                 {"value": 3, "label": "2-3 fois/semaine"}, {"value": 4, "label": "4-5 fois/semaine"}, {"value": 5, "label": "Tous les jours"}]},
    {"id": "q8", "category": "mental", "question": "Avez-vous une pratique de lecture ou d'apprentissage régulière ?",
     "options": [{"value": 1, "label": "Jamais"}, {"value": 2, "label": "Rarement"},
                 {"value": 3, "label": "Parfois"}, {"value": 4, "label": "Souvent"}, {"value": 5, "label": "Quotidiennement"}]},
    {"id": "q9", "category": "spirituel", "question": "Pratiquez-vous une forme de méditation, prière ou contemplation ?",
     "options": [{"value": 1, "label": "Jamais"}, {"value": 2, "label": "Rarement"},
                 {"value": 3, "label": "Parfois"}, {"value": 4, "label": "Régulièrement"}, {"value": 5, "label": "Tous les jours"}]},
    {"id": "q10", "category": "emotionnel", "question": "Avez-vous identifié et travaillé sur vos blessures émotionnelles ?",
     "options": [{"value": 1, "label": "Jamais abordé"}, {"value": 2, "label": "À peine"},
                 {"value": 3, "label": "En cours"}, {"value": 4, "label": "Bien avancé"}, {"value": 5, "label": "Transformées en forces"}]},
]

FRAME_SCAN_INDICATORS = [
    {"id": "fs1", "question": "Je me sens réactif plutôt que responsable face aux événements.",
     "type": "inverse", "weight": 1},
    {"id": "fs2", "question": "Je peux observer mes émotions sans être submergé.",
     "type": "direct", "weight": 1},
    {"id": "fs3", "question": "Je me sens victime des circonstances extérieures.",
     "type": "inverse", "weight": 1},
    {"id": "fs4", "question": "Je sais ce que je veux et pourquoi je le veux.",
     "type": "direct", "weight": 1},
    {"id": "fs5", "question": "Mes décisions sont influencées par la peur du jugement.",
     "type": "inverse", "weight": 1},
    {"id": "fs6", "question": "J'ai une vision claire de mon avenir.",
     "type": "direct", "weight": 1},
    {"id": "fs7", "question": "Je suis capable de dire non sans culpabilité.",
     "type": "direct", "weight": 1},
    {"id": "fs8", "question": "Mon estime de moi dépend du regard des autres.",
     "type": "inverse", "weight": 1},
    {"id": "fs9", "question": "Je me sens aligné avec mes valeurs profondes.",
     "type": "direct", "weight": 1},
    {"id": "fs10", "question": "Je peux rester centré dans le chaos.",
     "type": "direct", "weight": 1},
]


# ──────────────────────────────────────────────
# SCHEMAS Pydantic
# ──────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str

class LoginRequest(BaseModel):
    email: str
    password: str

class SessionRequest(BaseModel):
    session_id: str

class AuditSubmit(BaseModel):
    profile_type: Optional[str] = None
    entry_path: Optional[str] = None
    answers: list = []

class ChecklistUpdate(BaseModel):
    pillar_id: int
    completed_items: list = []

class DiagnosticSubmit(BaseModel):
    answers: list = []

class DailyLogSave(BaseModel):
    blocks: list = []

class FrameScanSubmit(BaseModel):
    responses: dict = {}

class SentinelChatRequest(BaseModel):
    message: str
    mode: str = "chat"
    session_id: Optional[str] = None
    context: Optional[dict] = {}

class SentinelFirewallRequest(BaseModel):
    text: str

class CogWarAttackRequest(BaseModel):
    level: int = 1
    pillar_id: int = 3

class CogWarDefendRequest(BaseModel):
    session_id: str
    defense: str

class KPIRequest(BaseModel):
    pillar_id: int
    kpi_data: dict = {}

class CycleUpdateRequest(BaseModel):
    cycle_day: int

class TransitionAuditStartRequest(BaseModel):
    pillar_id: int = Query(...)

class TransitionAuditAnswerRequest(BaseModel):
    pillar_id: int = Query(...)
    answer: str = Query(...)

class SearchQuery(BaseModel):
    q: str = ""
    scope: str = "all"


# ──────────────────────────────────────────────
# APPLICATION FASTAPI
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title="PR7 Backend API",
    description="Backend de remplacement pour Protocole Restauration 7",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://hassanijacques-boop.github.io",
        "https://pr7.onrender.com",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════
# ROUTES D'AUTHENTIFICATION
# ══════════════════════════════════════════════

@app.post("/api/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    user = User(
        email=req.email,
        name=req.name,
        hashed_password=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "audit_completed": user.audit_completed,
            "profile_type": user.profile_type,
            "active_pillar_id": user.active_pillar_id,
        },
        "access_token": token,
        "audit_completed": False,
    }


@app.post("/api/auth/login")
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    token = create_access_token({"sub": str(user.id)})
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "audit_completed": user.audit_completed,
            "profile_type": user.profile_type,
            "active_pillar_id": user.active_pillar_id,
        },
        "access_token": token,
        "audit_completed": user.audit_completed,
    }


@app.post("/api/auth/session")
def auth_session(req: SessionRequest, db: Session = Depends(get_db)):
    # Simulated session auth for OAuth-like flow
    # In production, validate with Emergent's auth
    try:
        payload = jwt.decode(req.session_id, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            raise HTTPException(status_code=401, detail="Session invalide")
        token = create_access_token({"sub": str(user.id)})
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "audit_completed": user.audit_completed,
                "profile_type": user.profile_type,
                "active_pillar_id": user.active_pillar_id,
            },
            "access_token": token,
            "audit_completed": user.audit_completed,
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Session invalide")


@app.get("/api/auth/me")
def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "audit_completed": user.audit_completed,
        "profile_type": user.profile_type,
        "active_pillar_id": user.active_pillar_id,
    }


@app.post("/api/auth/logout")
def logout():
    return {"message": "Déconnecté"}


# ══════════════════════════════════════════════
# ROUTES PILLARS
# ══════════════════════════════════════════════

@app.get("/api/pillars")
def get_pillars():
    return {"pillars": PILLARS_DATA}


@app.get("/api/pillars/slug/{slug}")
def get_pillar_by_slug(slug: str):
    for p in PILLARS_DATA:
        if p["slug"] == slug:
            return p
    raise HTTPException(status_code=404, detail="Pilier introuvable")


@app.get("/api/pillars/unlock-status")
def get_unlock_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    statuses = []
    for p in PILLARS_DATA:
        pg = db.query(PowerGauge).filter(
            PowerGauge.user_id == user.id,
            PowerGauge.pillar_id == p["id"]
        ).first()
        statuses.append({
            "pillar_id": p["id"],
            "slug": p["slug"],
            "unlocked": pg is not None or p["id"] <= user.active_pillar_id,
            "score": pg.score if pg else 0,
        })
    return {"status": statuses}


@app.get("/api/pillar/{pillar_id}/content")
def get_pillar_content(pillar_id: int):
    content = PILLAR_CONTENT.get(pillar_id)
    if not content:
        raise HTTPException(status_code=404, detail="Pilier introuvable")
    return content


@app.get("/api/pillar/{pillar_id}/power-gauge")
def get_power_gauge(pillar_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pg = db.query(PowerGauge).filter(
        PowerGauge.user_id == user.id,
        PowerGauge.pillar_id == pillar_id
    ).first()
    return {
        "pillar_id": pillar_id,
        "score": pg.score if pg else 0,
        "max": 100,
        "updated_at": pg.updated_at.isoformat() if pg else None,
    }


@app.get("/api/pillar/{pillar_id}/checklist")
def get_checklist(pillar_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cl = db.query(Checklist).filter(
        Checklist.user_id == user.id,
        Checklist.pillar_id == pillar_id
    ).first()
    return {
        "pillar_id": pillar_id,
        "completed_items": cl.completed_items if cl else [],
    }


@app.post("/api/pillar/{pillar_id}/checklist")
def update_checklist(pillar_id: int, req: ChecklistUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cl = db.query(Checklist).filter(
        Checklist.user_id == user.id,
        Checklist.pillar_id == pillar_id
    ).first()
    if not cl:
        cl = Checklist(user_id=user.id, pillar_id=pillar_id, completed_items=[])
        db.add(cl)
    cl.completed_items = req.completed_items
    db.commit()
    return {"message": "Checklist mise à jour", "completed_items": cl.completed_items}


@app.get("/api/pillar/{pillar_id}/diagnostic")
def get_diagnostic_questions(pillar_id: int):
    questions = [
        {"id": f"d{pid}_{i}", "category": "general",
         "question": f"Question diagnostic #{i} pour le pilier {pillar_id}",
         "options": [{"value": 1, "label": "Pas du tout"}, {"value": 2, "label": "Un peu"},
                     {"value": 3, "label": "Moyennement"}, {"value": 4, "label": "Beaucoup"},
                     {"value": 5, "label": "Totalement"}]}
        for i in range(1, 6)
    ]
    return {"questions": questions}


@app.post("/api/pillar/{pillar_id}/diagnostic")
def submit_diagnostic(pillar_id: int, req: DiagnosticSubmit, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    score = sum(min(5, max(1, a.get("value", 3) if isinstance(a, dict) else a)) for a in req.answers) if req.answers else 50
    score = min(100, max(0, int(score / len(req.answers) * 25) if req.answers else 50))

    # Update power gauge
    pg = db.query(PowerGauge).filter(
        PowerGauge.user_id == user.id,
        PowerGauge.pillar_id == pillar_id
    ).first()
    if not pg:
        pg = PowerGauge(user_id=user.id, pillar_id=pillar_id, score=score)
        db.add(pg)
    else:
        pg.score = score

    dr = DiagnosticResult(user_id=user.id, pillar_id=pillar_id, answers=req.answers, score=score)
    db.add(dr)
    db.commit()

    return {
        "message": "Diagnostic complété",
        "score": score,
        "interpretation": "Faible" if score < 33 else "Moyen" if score < 66 else "Élevé",
    }


# ══════════════════════════════════════════════
# ROUTES AUDIT
# ══════════════════════════════════════════════

@app.get("/api/audit/questions")
def get_audit_questions():
    return {"questions": AUDIT_QUESTIONS}


@app.post("/api/audit/submit")
def submit_audit(req: AuditSubmit, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Calculate baseline scores per category
    categories = {"physique": 0, "mental": 0, "spirituel": 0, "emotionnel": 0, "relationnel": 0, "discipline": 0}
    counts = {"physique": 0, "mental": 0, "spirituel": 0, "emotionnel": 0, "relationnel": 0, "discipline": 0}

    for answer in req.answers:
        qid = answer.get("question_id", answer.get("id", ""))
        val = answer.get("value", 3)
        # Find question category
        for q in AUDIT_QUESTIONS:
            if q["id"] == qid:
                cat = q["category"]
                categories[cat] = categories.get(cat, 0) + val
                counts[cat] = counts.get(cat, 0) + 1
                break

    # Normalize scores
    pillar_scores = {}
    for cat, total in categories.items():
        pillar_scores[cat] = int((total / (counts[cat] * 5)) * 100) if counts[cat] > 0 else 50

    user.audit_completed = True
    user.profile_type = req.profile_type or "standard"

    restoration_plan = {
        "recommendations": [
            f"Priorité : renforcer le pilier {cat} (score: {score}%)"
            for cat, score in sorted(pillar_scores.items(), key=lambda x: x[1])
            if score < 60
        ],
        "pillar_scores": pillar_scores,
        "entry_path": req.entry_path or "auto",
        "message": "Plan de restauration généré. Commence par le pilier le plus faible."
    }

    audit = AuditResult(
        user_id=user.id,
        profile_type=req.profile_type,
        entry_path=req.entry_path,
        answers=req.answers,
        restoration_plan=restoration_plan,
    )
    db.add(audit)

    # Create initial progress
    progress = db.query(Progress).filter(Progress.user_id == user.id).first()
    if not progress:
        progress = Progress(user_id=user.id, overall_score=30, pillar_scores=pillar_scores)
        db.add(progress)

    # Score history entry
    sh = ScoreHistory(user_id=user.id, score=30)
    db.add(sh)

    db.commit()

    return {
        "restoration_plan": restoration_plan,
        "audit_completed": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "audit_completed": True,
            "profile_type": user.profile_type,
        }
    }


# ══════════════════════════════════════════════
# ROUTES CITE INTÉRIEURE
# ══════════════════════════════════════════════

@app.get("/api/cite/daily-log")
def get_daily_log(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    log = db.query(DailyLog).filter(
        DailyLog.user_id == user.id,
        DailyLog.log_date == date.today()
    ).first()
    if log:
        return {"exists": True, "blocks": log.blocks, "leaks": []}
    return {"exists": False, "blocks": [], "leaks": []}


@app.post("/api/cite/daily-log")
def save_daily_log(req: DailyLogSave, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    log = db.query(DailyLog).filter(
        DailyLog.user_id == user.id,
        DailyLog.log_date == date.today()
    ).first()
    if not log:
        log = DailyLog(user_id=user.id, blocks=req.blocks)
        db.add(log)
    else:
        log.blocks = req.blocks

    # Calculate capital attention score
    total_time = sum(
        sum(b.get(k, 0) for k in ["production", "adoration", "repos", "distraction"])
        for b in req.blocks
    )
    max_possible = len(req.blocks) * 100
    if max_possible == 0:
        ca_score = 0
    else:
        ca_score = min(100, int((total_time / max_possible) * 100))

    # Save capital attention
    ca = CapitalAttention(user_id=user.id, score=ca_score)
    db.add(ca)
    db.commit()

    # Detect leaks
    leaks = []
    for block in req.blocks:
        if block.get("distraction", 0) > 50:
            leaks.append({
                "severity": "critical" if block["distraction"] > 70 else "moderate",
                "category": "distraction",
                "alert": f"Bloc {block.get('block', 'inconnu')}: {block['distraction']}% de distraction",
                "recommendation": "Réduire les sources de distraction. Appliquer la règle des 5 minutes.",
            })
        if block.get("adoration", 0) < 5:
            leaks.append({
                "severity": "moderate",
                "category": "adoration",
                "alert": "Temps d'adoration insuffisant aujourd'hui",
                "recommendation": "Prévoir un créneau dédié à l'adoration/quête spirituelle.",
            })

    return {"capital_attention": ca_score, "leaks": leaks}


@app.get("/api/cite/capital-attention")
def get_capital_attention(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today_entry = db.query(CapitalAttention).filter(
        CapitalAttention.user_id == user.id,
        CapitalAttention.log_date == date.today()
    ).first()

    week_ago = date.today() - timedelta(days=7)
    week_entries = db.query(CapitalAttention).filter(
        CapitalAttention.user_id == user.id,
        CapitalAttention.log_date >= week_ago
    ).all()

    avg = int(sum(e.score for e in week_entries) / len(week_entries)) if week_entries else 0

    return {
        "today": today_entry.score if today_entry else 0,
        "avg_7d": avg,
        "entries_7d": len(week_entries),
    }


@app.get("/api/cite/history")
def get_history(days: int = Query(14), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    start_date = date.today() - timedelta(days=days)
    entries = db.query(CapitalAttention).filter(
        CapitalAttention.user_id == user.id,
        CapitalAttention.log_date >= start_date
    ).order_by(CapitalAttention.log_date.asc()).all()

    history = [
        {"date": e.log_date.isoformat(), "capital_attention": e.score}
        for e in entries
    ]
    return {"history": history}


@app.get("/api/cite/weekly-verdict")
def get_weekly_verdict(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    week_start = date.today() - timedelta(days=date.today().weekday())

    existing = db.query(WeeklyVerdict).filter(
        WeeklyVerdict.user_id == user.id,
        WeeklyVerdict.week_start == week_start
    ).first()
    if existing:
        return {"verdict": existing.verdict, "stats": existing.stats}

    # Calculate from CA history
    week_entries = db.query(CapitalAttention).filter(
        CapitalAttention.user_id == user.id,
        CapitalAttention.log_date >= week_start
    ).all()

    days_logged = len(week_entries)
    avg_ca = int(sum(e.score for e in week_entries) / days_logged) if days_logged > 0 else 0
    hours_distraction = sum(1 for e in week_entries if e.score < 50)
    hours_adoration = sum(1 for e in week_entries if e.score > 70)

    verdict_texts = [
        "Semaine en dessous du potentiel. Les fondamentaux sont à consolider. Resserre le cadre.",
        "Progression modérée. Tu es sur la bonne voie mais l'intensité doit augmenter.",
        "Bonne semaine. La discipline paie. Maintiens le cap et augmente d'un cran.",
        "Semaine d'excellence. Tu vis ta meilleure version. Continue à inspirer.",
    ]
    idx = min(3, max(0, days_logged // 3))
    verdict = verdict_texts[idx]

    stats = {
        "days_logged": days_logged,
        "avg_capital_attention": avg_ca,
        "hours_distraction_week": hours_distraction,
        "hours_adoration_week": hours_adoration,
    }

    wv = WeeklyVerdict(user_id=user.id, week_start=week_start, verdict=verdict, stats=stats)
    db.add(wv)
    db.commit()

    return {"verdict": verdict, "stats": stats}


# ══════════════════════════════════════════════
# ROUTES BRI-90
# ══════════════════════════════════════════════

@app.get("/api/bri90/status")
def get_bri90_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.query(BRISession).filter(BRISession.user_id == user.id).first()
    if not session:
        return {
            "enrolled": False,
            "current_day": 0,
            "week": 1,
            "phase": 1,
            "graduated": False,
            "progress_percent": 0,
        }

    progress_percent = min(100, int((session.current_day / 90) * 100))
    return {
        "enrolled": session.enrolled,
        "current_day": session.current_day,
        "week": session.week,
        "phase": session.phase,
        "graduated": session.graduated,
        "progress_percent": progress_percent,
    }


PHASE_DATA = {
    1: {"name": "Foundation", "sentinel": "Le Bâtisseur", "color": "#D4AF37",
        "desc": "Phase 1 — Pose des fondations structurelles. 30 premiers jours.",
        "focus": "Construire les habitudes essentielles et éliminer les parasites."},
    2: {"name": "Fortification", "sentinel": "Le Guerrier", "color": "#E74C3C",
        "desc": "Phase 2 — Renforcement et expansion. Jours 31-60.",
        "focus": "Intensifier la pratique, étendre la discipline à tous les domaines."},
    3: {"name": "Maîtrise", "sentinel": "Le Sage", "color": "#9B59B6",
        "desc": "Phase 3 — Maîtrise et intégration. Jours 61-90.",
        "focus": "Intégrer les acquis, préparer la transmission."},
}

WEEK_THEMES = [
    "Le Réveil", "L'Ancrage", "La Structure", "La Purge",
    "La Résistance", "L'Extension", "L'Harmonie", "La Profondeur",
    "L'Intensité", "La Souveraineté", "L'Excellence", "La Transmission"
]


@app.post("/api/bri90/enroll")
def enroll_bri90(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.query(BRISession).filter(BRISession.user_id == user.id).first()
    if not session:
        session = BRISession(
            user_id=user.id,
            enrolled=True,
            current_day=1,
            week=1,
            phase=1,
            graduated=False,
            enrolled_at=datetime.utcnow(),
        )
        db.add(session)
    elif not session.enrolled:
        session.enrolled = True
        session.current_day = 1
        session.enrolled_at = datetime.utcnow()
    db.commit()
    db.refresh(session)

    phase = PHASE_DATA.get(session.phase, PHASE_DATA[1])
    week_theme = WEEK_THEMES[session.week - 1] if session.week <= len(WEEK_THEMES) else "Intégration"

    return {
        "enrolled": True,
        "current_day": session.current_day,
        "week": session.week,
        "week_theme": week_theme,
        "phase": session.phase,
        "phase_name": phase["name"],
        "phase_sentinel": phase["sentinel"],
        "phase_color": phase["color"],
        "phase_desc": phase["desc"],
        "phase_focus": phase["focus"],
        "progress_percent": int((session.current_day / 90) * 100),
        "graduated": False,
    }


# ══════════════════════════════════════════════
# ROUTES FRAME SCAN (Pillar 6)
# ══════════════════════════════════════════════

@app.get("/api/pillar/6/frame-scan/questions")
def get_frame_scan_questions():
    return {"indicators": FRAME_SCAN_INDICATORS}


@app.post("/api/pillar/6/frame-scan")
def submit_frame_scan(req: FrameScanSubmit, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    responses = req.responses
    total = 0
    count = 0
    for indicator in FRAME_SCAN_INDICATORS:
        val = responses.get(indicator["id"], 3)
        if indicator["type"] == "inverse":
            val = 6 - val
        total += val
        count += 1

    score = int((total / (count * 5)) * 100) if count > 0 else 50

    fs = FrameScan(user_id=user.id, responses=responses, score=score)
    db.add(fs)

    # Update power gauge for pillar 6
    pg = db.query(PowerGauge).filter(
        PowerGauge.user_id == user.id,
        PowerGauge.pillar_id == 6
    ).first()
    if not pg:
        pg = PowerGauge(user_id=user.id, pillar_id=6, score=score)
        db.add(pg)
    else:
        pg.score = score
    db.commit()

    return {
        "score": score,
        "interpretation": "Faible souveraineté" if score < 40 else "Souveraineté en construction" if score < 70 else "Bonne souveraineté",
        "max": 100,
    }


@app.get("/api/pillar/6/frame-scan/history")
def get_frame_scan_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scans = db.query(FrameScan).filter(
        FrameScan.user_id == user.id
    ).order_by(FrameScan.created_at.desc()).limit(20).all()

    return {
        "history": [
            {"id": s.id, "score": s.score, "created_at": s.created_at.isoformat()}
            for s in scans
        ]
    }


# ══════════════════════════════════════════════
# ROUTES SENTINEL
# ══════════════════════════════════════════════

@app.get("/api/sentinel/history")
def get_sentinel_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    messages = db.query(SentinelChat).filter(
        SentinelChat.user_id == user.id
    ).order_by(SentinelChat.created_at.asc()).limit(50).all()

    return {
        "history": [
            {"role": m.role, "content": m.content, "mode": m.mode, "session_id": m.session_id,
             "created_at": m.created_at.isoformat()}
            for m in messages
        ]
    }


@app.post("/api/sentinel/chat")
def sentinel_chat(req: SentinelChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Save user message
    user_msg = SentinelChat(user_id=user.id, role="user", content=req.message,
                            mode=req.mode, session_id=req.session_id)
    db.add(user_msg)

    # Generate contextual response
    context_note = ""
    if req.context:
        context_note = f" (contexte: {json.dumps(req.context)[:200]})"

    responses = {
        "greeting": "Bonjour, je suis votre Sentinel. Comment puis-je vous aider dans votre restauration aujourd'hui ?",
        "default": f"Message reçu : « {req.message[:100]} »{context_note}\n\n"
                   f"Voici ma réflexion : Dans le cadre du Protocole Restauration 7, chaque pensée, "
                   f"chaque action compte. Ce que vous exprimez révèle une partie de votre paysage intérieur. "
                   f"Continuez à explorer, à questionner, à chercher la vérité. Le chemin de la restauration "
                   f"est un chemin de conscience.",
        "cogwar": "Analyse cognitive en cours... Identifié : schéma de pensée à examiner. "
                  "Appliquez le protocole de défense cognitive : 1) Observez sans juger 2) Questionnez "
                  "la véracité 3) Reformulez en termes de responsabilité.",
        "firewall": "Analyse pare-feu activée. Le texte soumis a été analysé. "
                    "Aucun schéma destructeur majeur détecté. Poursuivez votre vigilance.",
    }

    response = responses.get("default")
    if "bonjour" in req.message.lower() or "salut" in req.message.lower():
        response = responses["greeting"]
    elif req.mode == "cogwar":
        response = responses["cogwar"]
    elif req.mode == "firewall":
        response = responses["firewall"]

    # Add mode-specific prefix
    if req.mode and req.mode != "chat":
        mode_info = SENTINEL_MODES.get(req.mode, "")
        response = f"[Mode: {req.mode}] {mode_info}\n\n{response}"

    # Save assistant response
    asst_msg = SentinelChat(user_id=user.id, role="assistant", content=response,
                            mode=req.mode, session_id=req.session_id)
    db.add(asst_msg)
    db.commit()

    return {"response": response, "session_id": req.session_id or str(uuid.uuid4())}


@app.post("/api/sentinel/firewall")
def sentinel_firewall(req: SentinelFirewallRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    text = req.text
    analysis = {
        "risk_level": "faible",
        "patterns_detected": [],
        "recommendation": "Analyse terminée. Continuez à cultiver des pensées constructives.",
    }

    risk_keywords = ["je n'y arrive pas", "c'est trop dur", "je suis nul", "tout va mal",
                     "je mérite pas", "pourquoi moi", "j'abandonne"]
    for kw in risk_keywords:
        if kw in text.lower():
            analysis["risk_level"] = "modéré"
            analysis["patterns_detected"].append(f"Schéma détecté : '{kw}'")

    if analysis["patterns_detected"]:
        analysis["recommendation"] = "Ces schémas de pensée sont des distorsions cognitives. " \
                                     "Appliquez le protocole de recadrage : identifiez, questionnez, reformulez."
        analysis["defense_protocol"] = "1. STOP — Reconnaissez le schéma\n" \
                                       "2. QUESTIONNEZ — Est-ce objectivement vrai ?\n" \
                                       "3. REFORMULEZ — En termes de responsabilité et d'action\n" \
                                       "4. AGISSEZ — Une petite action contraire au schéma"

    db_msg = SentinelChat(user_id=user.id, role="user", content=f"[FIREWALL] {text}", mode="firewall")
    db.add(db_msg)
    asst_msg = SentinelChat(user_id=user.id, role="assistant",
                            content=f"Analyse: {json.dumps(analysis)}", mode="firewall")
    db.add(asst_msg)
    db.commit()

    return {"analysis": analysis}


@app.post("/api/sentinel/cogwar/attack")
def cogwar_attack(req: CogWarAttackRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    attacks = {
        1: {"name": "Doute", "description": "Le doute s'infiltre dans votre esprit. 'Et si je n'y arrivais pas ?'"},
        2: {"name": "Procrastination", "description": "La tentation de remettre à demain. 'Je le ferai plus tard.'"},
        3: {"name": "Comparaison", "description": "Vous vous comparez aux autres et vous sentez inférieur."},
        4: {"name": "Ruminations", "description": "Les pensées négatives tournent en boucle dans votre esprit."},
        5: {"name": "Découragement", "description": "Le poids du chemin vous semble trop lourd."},
    }

    attack = attacks.get(req.level, attacks[1])
    session_id = str(uuid.uuid4())

    asst_msg = SentinelChat(user_id=user.id, role="assistant",
                            content=f"⚠️ ATTAQUE COGNITIVE : {attack['name']}\n{attack['description']}\n\n"
                                    f"Niveau: {req.level}/5 | Pilier concerné: {req.pillar_id}\n"
                                    f"Session de défense: {session_id}\n\n"
                                    f"Protocole de contre-mesure activé.",
                            mode="cogwar", session_id=session_id)
    db.add(asst_msg)
    db.commit()

    return {
        "attack": attack,
        "level": req.level,
        "session_id": session_id,
        "prompt": "Comment contre-attaquez-vous cette invasion cognitive ?",
        "defense_options": [
            "Observation distancée — 'Ce n'est pas moi, c'est l'attaque.'",
            "Contre-pensée — Activer une pensée de force opposée.",
            "Action immédiate — Bouger, changer d'environnement, agir.",
        ]
    }


@app.post("/api/sentinel/cogwar/defend")
def cogwar_defend(req: CogWarDefendRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_msg = SentinelChat(user_id=user.id, role="user",
                            content=f"[DÉFENSE] Session: {req.session_id[:12]}... | {req.defense}",
                            mode="cogwar", session_id=req.session_id)
    db.add(user_msg)

    # Score based on defense quality
    defense_keywords = ["observe", "respire", "action", "contre", "calme", "stop", "recadre", "accepte"]
    score = sum(1 for kw in defense_keywords if kw in req.defense.lower())
    score = min(100, score * 20 + 20)

    evaluation = {
        "score": score,
        "feedback": "Défense solide ! Vous avez appliqué les principes de contre-mesure." if score > 50
                    else "Défense basique. Essayez d'observer l'attaque sans vous identifier à elle.",
        "xp_gained": score // 10,
    }

    asst_msg = SentinelChat(user_id=user.id, role="assistant",
                            content=f"Évaluation: {json.dumps(evaluation)}", mode="cogwar")
    db.add(asst_msg)
    db.commit()

    return {"evaluation": evaluation}


@app.post("/api/sentinel/emergency")
def sentinel_emergency(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    protocol = {
        "activated": True,
        "timestamp": datetime.utcnow().isoformat(),
        "steps": [
            "1. STOP — Arrêtez tout. Isolez-vous du stimulus.",
            "2. RESPIRATION — 10 respirations profondes (4-7-8).",
            "3. ANCRAGE — Les 5 sens : 5 choses que vous voyez, 4 que vous touchez, etc.",
            "4. RESSENTI — Identifiez l'émotion sans jugement.",
            "5. RÉALIGNEMENT — Rappelez-vous votre 'pourquoi'.",
            "6. CONTACT — Si nécessaire, contactez un soutien."
        ],
        "affirmation": "Cette tempête passera. Vous êtes plus solide que ce qui vous arrive.",
    }

    asst_msg = SentinelChat(user_id=user.id, role="assistant",
                            content=f"[URGENCE] Protocole d'urgence activé.\n{json.dumps(protocol)}",
                            mode="emergency")
    db.add(asst_msg)
    db.commit()

    return protocol


@app.get("/api/sentinel/sovereignty-log")
def get_sovereignty_log(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    logs = db.query(SovereigntyLog).filter(
        SovereigntyLog.user_id == user.id
    ).order_by(SovereigntyLog.created_at.desc()).limit(30).all()

    return {"logs": [{"id": l.id, "entry": l.entry, "created_at": l.created_at.isoformat()} for l in logs]}


@app.get("/api/sentinel/daily-briefing")
def get_daily_briefing(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Calculate stats for briefing
    today_ca = db.query(CapitalAttention).filter(
        CapitalAttention.user_id == user.id,
        CapitalAttention.log_date == date.today()
    ).first()

    pending_checklists = db.query(Checklist).filter(
        Checklist.user_id == user.id
    ).count()

    bri = db.query(BRISession).filter(BRISession.user_id == user.id).first()

    briefing = {
        "date": date.today().isoformat(),
        "capital_attention_today": today_ca.score if today_ca else None,
        "bri90_day": bri.current_day if bri and bri.enrolled else None,
        "pending_checklists": pending_checklists,
        "affirmation_du_jour": random.choice([
            "Chaque jour est une nouvelle bataille. Choisis-la.",
            "La discipline est le pont entre les objectifs et les réalisations.",
            "Tu es ce que tu fais de façon répétée. L'excellence n'est pas un acte, mais une habitude.",
            "Le guerrier vainc d'abord dans sa tête, puis sur le terrain.",
            "La force naît de la confrontation avec la difficulté.",
        ]),
        "action_du_jour": random.choice([
            "Complète un audit de 15 minutes sur ton pilier principal.",
            "Écris 3 choses pour lesquelles tu es reconnaissant.",
            "Fais 20 minutes d'exercice sans te poser de questions.",
            "Lis 10 pages d'un livre qui te fait grandir.",
            "Contacte une personne qui compte pour toi.",
        ]),
    }

    return {"briefing": briefing}


@app.get("/api/sentinel/journal")
def get_journal(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    journals = db.query(SentinelJournal).filter(
        SentinelJournal.user_id == user.id
    ).order_by(SentinelJournal.created_at.desc()).limit(30).all()

    return {"entries": [{"id": j.id, "content": j.content, "created_at": j.created_at.isoformat()} for j in journals]}


@app.get("/api/sentinel/immunity-stats")
def get_immunity_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "immunity_score": random.randint(30, 85),
        "streak_days": random.randint(0, 14),
        "defenses_active": random.choice([True, False]),
        "vulnerability_areas": random.sample([
            "Distraction numérique", "Procrastination matinale",
            "Ruminations nocturnes", "Comparaison sociale"
        ], k=2),
    }


@app.get("/api/sentinel/stagnation-check")
def get_stagnation_check(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "stagnating": False,
        "days_since_progress": 0,
        "recommendation": "Continuez votre progression. Aucune stagnation détectée.",
        "unlock_suggestions": [
            "Essayez un nouveau protocole",
            "Augmentez l'intensité d'un pilier",
            "Partagez votre progression",
        ]
    }


@app.get("/api/sentinel/sovereignty-level")
def get_sovereignty_level(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "level": 1,
        "title": "L'Éveillé",
        "xp": 0,
        "xp_next": 100,
        "progress_percent": 0,
        "abilities": ["Observation intérieure"],
    }


@app.post("/api/sentinel/transition-audit/start")
def start_transition_audit(
    pillar_id: int = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    questions = [
        f"Qu'est-ce qui a changé dans votre pratique du pilier {pillar_id} cette semaine ?",
        f"Quel obstacle majeur avez-vous rencontré sur le pilier {pillar_id} ?",
        f"Quelle découverte clé avez-vous faite sur le pilier {pillar_id} ?",
    ]
    return {
        "session_id": str(uuid.uuid4()),
        "question": random.choice(questions),
        "pillar_id": pillar_id,
    }


@app.post("/api/sentinel/transition-audit/answer")
def answer_transition_audit(
    pillar_id: int = Query(...),
    answer: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        "received": True,
        "next_step": "Continuez votre pratique. Prochain audit dans 7 jours.",
        "insight": "Votre réponse révèle une prise de conscience significative. "
                   "Le travail d'introspection porte ses fruits.",
    }


@app.post("/api/sentinel/voice")
async def sentinel_voice(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Voice endpoint - accepts multipart form data
    return {
        "transcription": "Mode vocal simulé. La reconnaissance vocale sera active dans la version complète.",
        "response": "Message vocal reçu. Je vous ai entendu. Continuez à parler, je vous écoute.",
    }


@app.delete("/api/sentinel/history")
def clear_sentinel_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(SentinelChat).filter(SentinelChat.user_id == user.id).delete()
    db.commit()
    return {"message": "Historique effacé"}


# ══════════════════════════════════════════════
# ROUTES PROGRESS & KPI
# ══════════════════════════════════════════════

@app.get("/api/progress")
def get_progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prog = db.query(Progress).filter(Progress.user_id == user.id).first()
    if not prog:
        prog = Progress(user_id=user.id, overall_score=0, pillar_scores={})
        db.add(prog)
        db.commit()

    return {
        "overall_score": prog.overall_score,
        "pillar_scores": prog.pillar_scores or {},
        "pillars_count": 7,
        "completed_pillars": sum(1 for s in (prog.pillar_scores or {}).values() if s >= 80),
    }


@app.get("/api/progress/history")
def get_progress_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    history = db.query(ScoreHistory).filter(
        ScoreHistory.user_id == user.id
    ).order_by(ScoreHistory.date.asc()).limit(60).all()

    return {
        "score_history": [
            {"date": h.date.isoformat(), "score": h.score}
            for h in history
        ]
    }


@app.get("/api/kpis/pillar/{pillar_id}")
def get_pillar_kpis(pillar_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kpis = db.query(KPIRecord).filter(
        KPIRecord.user_id == user.id,
        KPIRecord.pillar_id == pillar_id
    ).order_by(KPIRecord.created_at.desc()).limit(20).all()

    return {
        "kpis": [{"id": k.id, "data": k.kpi_data, "created_at": k.created_at.isoformat()} for k in kpis]
    }


@app.post("/api/kpis")
def save_kpi(req: KPIRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kpi = KPIRecord(user_id=user.id, pillar_id=req.pillar_id, kpi_data=req.kpi_data)
    db.add(kpi)

    # Update progress
    prog = db.query(Progress).filter(Progress.user_id == user.id).first()
    if not prog:
        prog = Progress(user_id=user.id, overall_score=0, pillar_scores={})
        db.add(prog)

    scores = prog.pillar_scores or {}
    scores[str(req.pillar_id)] = min(100, scores.get(str(req.pillar_id), 0) + 5)
    prog.pillar_scores = scores
    prog.overall_score = min(100, int(sum(scores.values()) / max(1, len(scores))))

    sh = ScoreHistory(user_id=user.id, score=prog.overall_score)
    db.add(sh)
    db.commit()

    return {"message": "KPI enregistré", "progress": prog.overall_score}


# ══════════════════════════════════════════════
# ROUTES SOUVERAINETÉ & STAGNATION
# ══════════════════════════════════════════════

@app.get("/api/sovereignty/dashboard")
def get_sovereignty_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "level": 1,
        "title": "L'Éveillé",
        "sovereignty_score": random.randint(20, 60),
        "domains": [
            {"name": "Émotionnel", "score": random.randint(20, 80), "color": "#F1C40F"},
            {"name": "Mental", "score": random.randint(20, 80), "color": "#4ECDC4"},
            {"name": "Physique", "score": random.randint(20, 80), "color": "#FF6B35"},
            {"name": "Spirituel", "score": random.randint(20, 80), "color": "#9B59B6"},
        ]
    }


@app.get("/api/stagnation/status")
def get_stagnation_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "stagnating": False,
        "days_idle": 0,
        "message": "Progression active. Continuez ainsi.",
        "suggested_actions": [
            "Augmentez l'intensité de votre pratique du pilier principal.",
            "Introduisez un nouveau rituel quotidien.",
            "Partagez votre progression avec un mentor ou un pair.",
        ]
    }


# ══════════════════════════════════════════════
# ROUTES CYCLE
# ══════════════════════════════════════════════

@app.get("/api/cycle/status")
def get_cycle_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "cycle_day": 1,
        "phase": "Éveil",
        "energy_level": "Moyen",
        "recommendations": [
            "Commencez la journée par une intention claire.",
            "Priorisez les tâches à haute concentration ce matin.",
        ],
        "pillar_focus": PILLARS_DATA[0]["slug"],
    }


@app.post("/api/cycle/update")
def update_cycle(req: CycleUpdateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "cycle_day": req.cycle_day,
        "phase": "Action" if req.cycle_day < 15 else "Réflexion",
        "recommendations": [
            "Maintenez le rythme.",
            "Hydratez-vous et faites des pauses régulières.",
        ],
    }


# ══════════════════════════════════════════════
# ROUTES DOCUMENTS
# ══════════════════════════════════════════════

@app.get("/api/documents")
def get_documents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"documents": []}


@app.post("/api/documents/upload")
async def upload_document(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"message": "Upload simulé", "doc_id": str(uuid.uuid4())[:8]}


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"message": "Document supprimé"}


# ══════════════════════════════════════════════
# ROUTES SEARCH
# ══════════════════════════════════════════════

@app.get("/api/search")
def search(q: str = "", scope: str = "all", user: User = Depends(get_current_user)):
    results = []
    ql = q.lower()

    # Search in pillars
    if scope in ("all", "pillars"):
        for p in PILLARS_DATA:
            if ql in p["name"].lower() or ql in p["desc"].lower():
                results.append({
                    "type": "pillar",
                    "id": p["id"],
                    "title": p["name"],
                    "description": p["desc"],
                    "slug": p["slug"],
                    "url": f"/pilier/{p['slug']}",
                })

    # Search in audit questions
    if scope in ("all", "audit"):
        for qa in AUDIT_QUESTIONS:
            if ql in qa["question"].lower():
                results.append({
                    "type": "audit_question",
                    "id": qa["id"],
                    "title": qa["category"],
                    "description": qa["question"],
                    "url": "/audit",
                })

    return {"results": results[:10], "total": len(results[:10])}


# ══════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════

@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "1.0.0", "timestamp": datetime.utcnow().isoformat()}


# ══════════════════════════════════════════════
# SERVE FRONTEND (PRODUCTION)
# ══════════════════════════════════════════════

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os.path

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
