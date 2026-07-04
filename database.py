from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = BASE_DIR / "app.db"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        database = current_app.config.get("DATABASE", DEFAULT_DATABASE)
        g.db = sqlite3.connect(database)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_error: Exception | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    return get_db().execute(sql, params).fetchone()


def query_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return get_db().execute(sql, params).fetchall()


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    db = get_db()
    cursor = db.execute(sql, params)
    db.commit()
    return cursor


SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('admin', 'docente')),
    activo INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS areas_curriculares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    nivel TEXT NOT NULL DEFAULT 'Inicial',
    ciclo TEXT NOT NULL DEFAULT 'I y II',
    tipo TEXT NOT NULL DEFAULT 'area curricular',
    orden INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1,
    descripcion TEXT
);

CREATE TABLE IF NOT EXISTS competencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    ciclo TEXT NOT NULL DEFAULT 'I y II',
    orden INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1,
    descripcion TEXT,
    FOREIGN KEY (area_id) REFERENCES areas_curriculares(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS capacidades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competencia_id INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    orden INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1,
    descripcion TEXT,
    FOREIGN KEY (competencia_id) REFERENCES competencias(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fichas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    institucion TEXT NOT NULL,
    docente TEXT NOT NULL,
    fecha TEXT NOT NULL,
    aula_edad TEXT NOT NULL,
    ciclo TEXT NOT NULL DEFAULT 'I y II',
    area_id INTEGER NOT NULL,
    competencia_id INTEGER NOT NULL,
    actividad TEXT NOT NULL,
    numero_grupo TEXT,
    numero_estudiantes INTEGER NOT NULL DEFAULT 0,
    integrantes TEXT,
    observaciones_generales TEXT,
    acciones_pedagogicas TEXT,
    analisis_interpretacion TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (area_id) REFERENCES areas_curriculares(id),
    FOREIGN KEY (competencia_id) REFERENCES competencias(id)
);

CREATE TABLE IF NOT EXISTS estudiantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ficha_id INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    orden INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (ficha_id) REFERENCES fichas(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS criterios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ficha_id INTEGER NOT NULL,
    capacidad_id INTEGER NOT NULL,
    descripcion TEXT NOT NULL,
    orden INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (ficha_id) REFERENCES fichas(id) ON DELETE CASCADE,
    FOREIGN KEY (capacidad_id) REFERENCES capacidades(id)
);

CREATE TABLE IF NOT EXISTS resultados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ficha_id INTEGER NOT NULL,
    estudiante_id INTEGER NOT NULL,
    criterio_id INTEGER NOT NULL,
    nivel TEXT NOT NULL CHECK (nivel IN ('AD', 'A', 'B', 'C')),
    evidencia TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (estudiante_id, criterio_id),
    FOREIGN KEY (ficha_id) REFERENCES fichas(id) ON DELETE CASCADE,
    FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
    FOREIGN KEY (criterio_id) REFERENCES criterios(id) ON DELETE CASCADE
);
"""


CATALOG_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_areas_catalogo
ON areas_curriculares(nombre, nivel, ciclo, tipo);

CREATE UNIQUE INDEX IF NOT EXISTS ux_competencias_catalogo
ON competencias(area_id, nombre, ciclo);

CREATE UNIQUE INDEX IF NOT EXISTS ux_capacidades_catalogo
ON capacidades(competencia_id, nombre);
"""


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()
    migrate_fichas_schema()
    migrate_catalog_schema()
    db.executescript(CATALOG_INDEXES)
    db.commit()
    from seed_cneb import seed_cneb

    seed_cneb()
    seed_users()


def table_columns(table_name: str) -> set[str]:
    return {row["name"] for row in get_db().execute(f"PRAGMA table_info({table_name})")}


def migrate_fichas_schema() -> None:
    db = get_db()
    if "ciclo" not in table_columns("fichas"):
        db.execute("ALTER TABLE fichas ADD COLUMN ciclo TEXT NOT NULL DEFAULT 'I y II'")
        db.commit()


def has_legacy_area_unique() -> bool:
    db = get_db()
    for index in db.execute("PRAGMA index_list(areas_curriculares)").fetchall():
        if not index["unique"]:
            continue
        columns = [
            row["name"]
            for row in db.execute(f"PRAGMA index_info({index['name']})").fetchall()
        ]
        if columns == ["nombre"]:
            return True
    return False


def migrate_catalog_schema() -> None:
    db = get_db()
    area_columns = table_columns("areas_curriculares")
    competencia_columns = table_columns("competencias")
    capacidad_columns = table_columns("capacidades")

    needs_rebuild = (
        "nivel" not in area_columns
        or "ciclo" not in area_columns
        or "tipo" not in area_columns
        or "orden" not in area_columns
        or "activo" not in area_columns
        or "ciclo" not in competencia_columns
        or "orden" not in competencia_columns
        or "activo" not in competencia_columns
        or "orden" not in capacidad_columns
        or "activo" not in capacidad_columns
        or has_legacy_area_unique()
    )
    if not needs_rebuild:
        db.executescript(CATALOG_INDEXES)
        db.commit()
        return

    db.execute("PRAGMA foreign_keys = OFF")
    db.executescript(
        """
        ALTER TABLE areas_curriculares RENAME TO areas_curriculares_old;
        ALTER TABLE competencias RENAME TO competencias_old;
        ALTER TABLE capacidades RENAME TO capacidades_old;

        CREATE TABLE areas_curriculares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            nivel TEXT NOT NULL DEFAULT 'Inicial',
            ciclo TEXT NOT NULL DEFAULT 'I y II',
            tipo TEXT NOT NULL DEFAULT 'area curricular',
            orden INTEGER NOT NULL DEFAULT 0,
            activo INTEGER NOT NULL DEFAULT 1,
            descripcion TEXT
        );

        CREATE TABLE competencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            area_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            ciclo TEXT NOT NULL DEFAULT 'I y II',
            orden INTEGER NOT NULL DEFAULT 0,
            activo INTEGER NOT NULL DEFAULT 1,
            descripcion TEXT,
            FOREIGN KEY (area_id) REFERENCES areas_curriculares(id) ON DELETE CASCADE
        );

        CREATE TABLE capacidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competencia_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            orden INTEGER NOT NULL DEFAULT 0,
            activo INTEGER NOT NULL DEFAULT 1,
            descripcion TEXT,
            FOREIGN KEY (competencia_id) REFERENCES competencias(id) ON DELETE CASCADE
        );

        INSERT INTO areas_curriculares (id, nombre, nivel, ciclo, tipo, orden, activo, descripcion)
        SELECT id, nombre, 'Inicial', 'I y II', 'area curricular', id, 1, descripcion
        FROM areas_curriculares_old;

        INSERT INTO competencias (id, area_id, nombre, ciclo, orden, activo, descripcion)
        SELECT id, area_id, nombre, 'I y II', id, 1, descripcion
        FROM competencias_old;

        INSERT INTO capacidades (id, competencia_id, nombre, orden, activo, descripcion)
        SELECT id, competencia_id, nombre, id, 1, descripcion
        FROM capacidades_old;

        DROP TABLE capacidades_old;
        DROP TABLE competencias_old;
        DROP TABLE areas_curriculares_old;

        CREATE UNIQUE INDEX ux_areas_catalogo
        ON areas_curriculares(nombre, nivel, ciclo, tipo);

        CREATE UNIQUE INDEX ux_competencias_catalogo
        ON competencias(area_id, nombre, ciclo);

        CREATE UNIQUE INDEX ux_capacidades_catalogo
        ON capacidades(competencia_id, nombre);
        """
    )
    db.commit()
    db.execute("PRAGMA foreign_keys = ON")


def seed_catalog() -> None:
    from seed_cneb import seed_cneb

    seed_cneb()


def seed_legacy_catalog() -> None:
    db = get_db()
    area_count = db.execute("SELECT COUNT(*) FROM areas_curriculares").fetchone()[0]
    if area_count:
        return


def seed_users() -> None:
    db = get_db()
    user_count = db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    if user_count:
        return

    users = [
        ("Administrador", "admin@miruta.local", "admin123", "admin"),
        ("Docente Demo", "docente@miruta.local", "docente123", "docente"),
    ]
    for nombre, email, password, rol in users:
        db.execute(
            """
            INSERT INTO usuarios (nombre, email, password_hash, rol)
            VALUES (?, ?, ?, ?)
            """,
            (nombre, email, generate_password_hash(password), rol),
        )
    db.commit()
