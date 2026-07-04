from __future__ import annotations

import json
from pathlib import Path

from database import get_db


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_JSON = BASE_DIR / "data" / "cneb_inicial.json"


def normalize(value: str | None, default: str = "") -> str:
    return (value or default).strip()


def load_catalog(path: Path = DEFAULT_JSON) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def upsert_area(area: dict) -> int:
    db = get_db()
    nombre = normalize(area.get("nombre"))
    nivel = normalize(area.get("nivel"), "Inicial")
    ciclo = normalize(area.get("ciclo"), "I y II")
    tipo = normalize(area.get("tipo"), "area curricular")
    orden = int(area.get("orden") or 0)

    row = db.execute(
        """
        SELECT id FROM areas_curriculares
        WHERE nombre = ? AND nivel = ? AND ciclo = ? AND tipo = ?
        """,
        (nombre, nivel, ciclo, tipo),
    ).fetchone()
    if row:
        db.execute(
            """
            UPDATE areas_curriculares
            SET orden = ?, activo = 1
            WHERE id = ?
            """,
            (orden, row["id"]),
        )
        return row["id"]

    return db.execute(
        """
        INSERT INTO areas_curriculares (nombre, nivel, ciclo, tipo, orden, activo, descripcion)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """,
        (
            nombre,
            nivel,
            ciclo,
            tipo,
            orden,
            "Catalogo interno CNEB para Educacion Inicial",
        ),
    ).lastrowid


def upsert_competencia(area_id: int, competencia: dict) -> int:
    db = get_db()
    nombre = normalize(competencia.get("nombre"))
    ciclo = normalize(competencia.get("ciclo"), "I y II")
    orden = int(competencia.get("orden") or 0)

    row = db.execute(
        """
        SELECT id FROM competencias
        WHERE area_id = ? AND nombre = ? AND ciclo = ?
        """,
        (area_id, nombre, ciclo),
    ).fetchone()
    if row:
        db.execute(
            """
            UPDATE competencias
            SET orden = ?, activo = 1
            WHERE id = ?
            """,
            (orden, row["id"]),
        )
        return row["id"]

    return db.execute(
        """
        INSERT INTO competencias (area_id, nombre, ciclo, orden, activo)
        VALUES (?, ?, ?, ?, 1)
        """,
        (area_id, nombre, ciclo, orden),
    ).lastrowid


def upsert_capacidad(competencia_id: int, nombre: str, orden: int) -> int:
    db = get_db()
    nombre = normalize(nombre)
    row = db.execute(
        """
        SELECT id FROM capacidades
        WHERE competencia_id = ? AND nombre = ?
        """,
        (competencia_id, nombre),
    ).fetchone()
    if row:
        db.execute(
            """
            UPDATE capacidades
            SET orden = ?, activo = 1
            WHERE id = ?
            """,
            (orden, row["id"]),
        )
        return row["id"]

    return db.execute(
        """
        INSERT INTO capacidades (competencia_id, nombre, orden, activo)
        VALUES (?, ?, ?, 1)
        """,
        (competencia_id, nombre, orden),
    ).lastrowid


def seed_cneb(path: Path = DEFAULT_JSON) -> None:
    db = get_db()
    catalog = load_catalog(path)
    db.execute("UPDATE capacidades SET activo = 0")
    db.execute("UPDATE competencias SET activo = 0")
    db.execute("UPDATE areas_curriculares SET activo = 0")

    for area in catalog.get("areas", []):
        area_id = upsert_area(area)
        for competencia in area.get("competencias", []):
            competencia_id = upsert_competencia(area_id, competencia)
            for index, capacidad in enumerate(competencia.get("capacidades", []), start=1):
                upsert_capacidad(competencia_id, capacidad, index)

    db.commit()


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        seed_cneb()
        print("Catalogo CNEB Inicial cargado desde data/cneb_inicial.json.")
