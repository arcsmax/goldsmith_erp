#!/usr/bin/env python3
"""Seed-Data für Standard-Aktivitäten im Time-Tracking System"""

from datetime import datetime
from sqlalchemy.orm import Session
from .models import Activity

# Standard-Aktivitäten nach Kategorie
STANDARD_ACTIVITIES = [
    # Fabrication (Fertigung) - 7 Aktivitäten
    {
        "name": "Sägen",
        "category": "fabrication",
        "icon": "🪚",
        "color": "#FF6B6B",
        "is_custom": False,
        "created_by": None,
    },
    {
        "name": "Feilen",
        "category": "fabrication",
        "icon": "⚒️",
        "color": "#4ECDC4",
        "is_custom": False,
        "created_by": None,
    },
    {
        "name": "Löten",
        "category": "fabrication",
        "icon": "🔥",
        "color": "#FF8C42",
        "is_custom": False,
        "created_by": None,
    },
    {
        "name": "Polieren",
        "category": "fabrication",
        "icon": "✨",
        "color": "#95E1D3",
        "is_custom": False,
        "created_by": None,
    },
    {
        "name": "Fassen (Steine)",
        "category": "fabrication",
        "icon": "💎",
        "color": "#A8E6CF",
        "is_custom": False,
        "created_by": None,
    },
    {
        "name": "Gravieren",
        "category": "fabrication",
        "icon": "✍️",
        "color": "#FFD3B6",
        "is_custom": False,
        "created_by": None,
    },
    {
        "name": "Emaillieren",
        "category": "fabrication",
        "icon": "🎨",
        "color": "#FFAAA5",
        "is_custom": False,
        "created_by": None,
    },

    # Administration - 4 Aktivitäten
    {
        "name": "Kundenberatung",
        "category": "administration",
        "icon": "👥",
        "color": "#667EEA",
        "is_custom": False,
        "created_by": None,
    },
    {
        "name": "Angebot erstellen",
        "category": "administration",
        "icon": "📝",
        "color": "#764BA2",
        "is_custom": False,
        "created_by": None,
    },
    {
        "name": "Dokumentation",
        "category": "administration",
        "icon": "📋",
        "color": "#5C6AC4",
        "is_custom": False,
        "created_by": None,
    },
    {
        "name": "Qualitätskontrolle",
        "category": "administration",
        "icon": "🔍",
        "color": "#006BA6",
        "is_custom": False,
        "created_by": None,
    },

    # Waiting - 4 Aktivitäten
    {
        "name": "Warten auf Material",
        "category": "waiting",
        "icon": "⏳",
        "color": "#A0AEC0",
        "is_custom": False,
        "created_by": None,
    },
    {
        "name": "Warten auf Kundenfeedback",
        "category": "waiting",
        "icon": "💬",
        "color": "#718096",
        "is_custom": False,
        "created_by": None,
    },
    {
        "name": "Pause",
        "category": "waiting",
        "icon": "☕",
        "color": "#CBD5E0",
        "is_custom": False,
        "created_by": None,
    },
    {
        "name": "Unterbrechung",
        "category": "waiting",
        "icon": "⚠️",
        "color": "#E2E8F0",
        "is_custom": False,
        "created_by": None,
    },
]


def seed_activities(db: Session) -> None:
    """
    Erstellt die Standard-Aktivitäten in der Datenbank.
    Überspringt bereits existierende Aktivitäten.

    Args:
        db: SQLAlchemy Session
    """
    created_count = 0
    skipped_count = 0

    for activity_data in STANDARD_ACTIVITIES:
        # Prüfe ob Aktivität bereits existiert
        existing = db.query(Activity).filter(
            Activity.name == activity_data["name"],
            Activity.category == activity_data["category"]
        ).first()

        if existing:
            skipped_count += 1
            continue

        # Erstelle neue Aktivität
        activity = Activity(
            name=activity_data["name"],
            category=activity_data["category"],
            icon=activity_data["icon"],
            color=activity_data["color"],
            usage_count=0,
            is_custom=activity_data["is_custom"],
            created_by=activity_data["created_by"],
            created_at=datetime.utcnow()
        )

        db.add(activity)
        created_count += 1

    db.commit()

    print(f"✅ Seed-Data: {created_count} Aktivitäten erstellt, {skipped_count} übersprungen")


def main():
    """Standalone-Ausführung für Seed-Daten"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import os

    # Datenbankverbindung aus Environment
    database_url = os.getenv("DATABASE_URL", "postgresql://goldsmith:goldsmith@localhost/goldsmith_erp")

    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        seed_activities(db)
    except Exception as e:
        print(f"❌ Fehler beim Seeden: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
