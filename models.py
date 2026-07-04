from __future__ import annotations

from flask_login import UserMixin

from database import execute, query_all, query_one


class User(UserMixin):
    def __init__(self, row):
        self.id = str(row["id"])
        self.nombre = row["nombre"]
        self.email = row["email"]
        self.rol = row["rol"]
        self.activo = bool(row["activo"])

    @property
    def is_active(self) -> bool:
        return self.activo

    @property
    def is_admin(self) -> bool:
        return self.rol == "admin"


def get_user(user_id: str) -> User | None:
    row = query_one("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    return User(row) if row else None


def get_user_by_email(email: str):
    return query_one("SELECT * FROM usuarios WHERE email = ?", (email.lower().strip(),))


def cycle_matches_sql(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"({prefix}ciclo = ? OR {prefix}ciclo = 'I y II' OR ? = 'I y II')"


def list_areas(ciclo: str | None = None):
    if ciclo:
        return query_all(
            f"""
            SELECT * FROM areas_curriculares
            WHERE activo = 1 AND {cycle_matches_sql()}
            ORDER BY orden, tipo, nombre, ciclo
            """,
            (ciclo, ciclo),
        )
    return query_all(
        """
        SELECT * FROM areas_curriculares
        WHERE activo = 1
        ORDER BY orden, tipo, nombre, ciclo
        """
    )


def list_competencias(area_id: int, ciclo: str | None = None):
    if ciclo:
        return query_all(
            f"""
            SELECT * FROM competencias
            WHERE area_id = ? AND activo = 1 AND {cycle_matches_sql()}
            ORDER BY orden, nombre, ciclo
            """,
            (area_id, ciclo, ciclo),
        )
    return query_all(
        """
        SELECT * FROM competencias
        WHERE area_id = ? AND activo = 1
        ORDER BY orden, nombre, ciclo
        """,
        (area_id,),
    )


def list_capacidades(competencia_id: int):
    return query_all(
        """
        SELECT * FROM capacidades
        WHERE competencia_id = ? AND activo = 1
        ORDER BY orden, id
        """,
        (competencia_id,),
    )


def get_area(area_id: int):
    return query_one(
        "SELECT * FROM areas_curriculares WHERE id = ? AND activo = 1",
        (area_id,),
    )


def get_competencia(competencia_id: int, area_id: int | None = None):
    if area_id is None:
        return query_one(
            "SELECT * FROM competencias WHERE id = ? AND activo = 1",
            (competencia_id,),
        )
    return query_one(
        """
        SELECT * FROM competencias
        WHERE id = ? AND area_id = ? AND activo = 1
        """,
        (competencia_id, area_id),
    )


def get_capacidad(capacidad_id: int, competencia_id: int | None = None):
    if competencia_id is None:
        return query_one(
            "SELECT * FROM capacidades WHERE id = ? AND activo = 1",
            (capacidad_id,),
        )
    return query_one(
        """
        SELECT * FROM capacidades
        WHERE id = ? AND competencia_id = ? AND activo = 1
        """,
        (capacidad_id, competencia_id),
    )


def get_ficha(ficha_id: int, user) -> dict | None:
    if user.is_admin:
        row = query_one(
            """
            SELECT f.*,
                   COALESCE(a.nombre, 'Area no disponible') AS area_nombre,
                   a.nivel AS area_nivel,
                   a.ciclo AS area_ciclo,
                   a.tipo AS area_tipo,
                   COALESCE(c.nombre, 'Competencia no disponible') AS competencia_nombre,
                   c.ciclo AS competencia_ciclo,
                   u.nombre AS usuario_nombre
            FROM fichas f
            LEFT JOIN areas_curriculares a ON a.id = f.area_id
            LEFT JOIN competencias c ON c.id = f.competencia_id
            JOIN usuarios u ON u.id = f.usuario_id
            WHERE f.id = ?
            """,
            (ficha_id,),
        )
    else:
        row = query_one(
            """
            SELECT f.*,
                   COALESCE(a.nombre, 'Area no disponible') AS area_nombre,
                   a.nivel AS area_nivel,
                   a.ciclo AS area_ciclo,
                   a.tipo AS area_tipo,
                   COALESCE(c.nombre, 'Competencia no disponible') AS competencia_nombre,
                   c.ciclo AS competencia_ciclo,
                   u.nombre AS usuario_nombre
            FROM fichas f
            LEFT JOIN areas_curriculares a ON a.id = f.area_id
            LEFT JOIN competencias c ON c.id = f.competencia_id
            JOIN usuarios u ON u.id = f.usuario_id
            WHERE f.id = ? AND f.usuario_id = ?
            """,
            (ficha_id, int(user.id)),
        )
    return dict(row) if row else None


def list_fichas(user):
    if user.is_admin:
        return query_all(
            """
            SELECT f.*,
                   COALESCE(a.nombre, 'Area no disponible') AS area_nombre,
                   a.ciclo AS area_ciclo,
                   a.tipo AS area_tipo,
                   u.nombre AS usuario_nombre
            FROM fichas f
            LEFT JOIN areas_curriculares a ON a.id = f.area_id
            JOIN usuarios u ON u.id = f.usuario_id
            ORDER BY f.fecha DESC, f.id DESC
            """
        )
    return query_all(
        """
        SELECT f.*,
               COALESCE(a.nombre, 'Area no disponible') AS area_nombre,
               a.ciclo AS area_ciclo,
               a.tipo AS area_tipo,
               u.nombre AS usuario_nombre
        FROM fichas f
        LEFT JOIN areas_curriculares a ON a.id = f.area_id
        JOIN usuarios u ON u.id = f.usuario_id
        WHERE f.usuario_id = ?
        ORDER BY f.fecha DESC, f.id DESC
        """,
        (int(user.id),),
    )


def list_estudiantes(ficha_id: int):
    return query_all(
        "SELECT * FROM estudiantes WHERE ficha_id = ? ORDER BY orden, id",
        (ficha_id,),
    )


def sync_student_count(ficha_id: int) -> None:
    total = query_one("SELECT COUNT(*) AS total FROM estudiantes WHERE ficha_id = ?", (ficha_id,))[
        "total"
    ]
    execute("UPDATE fichas SET numero_estudiantes = ? WHERE id = ?", (total, ficha_id))


def list_criterios(ficha_id: int):
    return query_all(
        """
        SELECT cr.*,
               COALESCE(ca.nombre, 'Capacidad no disponible') AS capacidad_nombre,
               ca.orden AS capacidad_orden,
               COALESCE(co.nombre, 'Competencia no disponible') AS competencia_nombre,
               co.ciclo AS competencia_ciclo,
               COALESCE(ar.nombre, 'Area no disponible') AS area_nombre,
               ar.ciclo AS area_ciclo,
               ar.tipo AS area_tipo
        FROM criterios cr
        LEFT JOIN capacidades ca ON ca.id = cr.capacidad_id
        LEFT JOIN competencias co ON co.id = ca.competencia_id
        LEFT JOIN areas_curriculares ar ON ar.id = co.area_id
        WHERE cr.ficha_id = ?
        ORDER BY cr.orden, cr.id
        """,
        (ficha_id,),
    )


def list_resultados(ficha_id: int):
    return query_all(
        """
        SELECT r.*, e.nombre AS estudiante_nombre, cr.descripcion AS criterio_descripcion
        FROM resultados r
        JOIN estudiantes e ON e.id = r.estudiante_id
        JOIN criterios cr ON cr.id = r.criterio_id
        WHERE r.ficha_id = ?
        """,
        (ficha_id,),
    )
