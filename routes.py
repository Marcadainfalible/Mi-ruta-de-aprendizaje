from __future__ import annotations

from collections import defaultdict

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from database import execute, query_all, query_one
from models import (
    get_area,
    get_capacidad,
    get_competencia,
    get_ficha,
    list_areas,
    list_capacidades,
    list_competencias,
    list_criterios,
    list_estudiantes,
    list_fichas,
    list_resultados,
    sync_student_count,
)


main_bp = Blueprint("main", __name__)
LEVELS = ["AD", "A", "B", "C"]
LEVEL_LABELS = {
    "AD": "Logro destacado",
    "A": "Logro esperado",
    "B": "En proceso",
    "C": "En inicio",
}
LEVEL_ORDINAL = {"C": 1, "B": 2, "A": 3, "AD": 4}


def require_ficha(ficha_id: int) -> dict:
    ficha = get_ficha(ficha_id, current_user)
    if not ficha:
        abort(404)
    return ficha


def split_integrantes(text: str) -> list[str]:
    raw = text.replace("\r", "\n").replace(",", "\n").split("\n")
    return [item.strip() for item in raw if item.strip()]


def build_stats(ficha_id: int) -> dict:
    criterios = [dict(row) for row in list_criterios(ficha_id)]
    estudiantes = [dict(row) for row in list_estudiantes(ficha_id)]
    resultados = list_resultados(ficha_id)
    resultados_map = {
        (row["estudiante_id"], row["criterio_id"]): dict(row) for row in resultados
    }

    by_criterio = {criterio["id"]: {level: 0 for level in LEVELS} for criterio in criterios}
    evidencias = defaultdict(list)
    general = {level: 0 for level in LEVELS}
    evaluated_students = set()

    for row in resultados:
        nivel = row["nivel"]
        if row["criterio_id"] in by_criterio and nivel in LEVELS:
            by_criterio[row["criterio_id"]][nivel] += 1
            general[nivel] += 1
            evaluated_students.add(row["estudiante_id"])
        if row["evidencia"]:
            evidencias[row["criterio_id"]].append(row["evidencia"])

    criterion_rows = []
    for criterio in criterios:
        counts = by_criterio[criterio["id"]]
        total = sum(counts.values())
        percentages = {
            level: round((counts[level] / total) * 100, 1) if total else 0 for level in LEVELS
        }
        item = dict(criterio)
        item.update(
            {
                "counts": counts,
                "percentages": percentages,
                "total": total,
                "evidencias": evidencias[criterio["id"]],
            }
        )
        criterion_rows.append(item)

    general_total = sum(general.values())
    general_percentages = {
        level: round((general[level] / general_total) * 100, 1) if general_total else 0
        for level in LEVELS
    }

    return {
        "criterios": criterion_rows,
        "estudiantes": estudiantes,
        "individual_profiles": build_individual_profiles(estudiantes, criterios, resultados_map),
        "total_estudiantes": len(estudiantes),
        "total_evaluados": len(evaluated_students),
        "general_counts": general,
        "general_percentages": general_percentages,
        "general_total": general_total,
        "levels": LEVELS,
        "level_labels": LEVEL_LABELS,
    }


def build_individual_profiles(estudiantes: list[dict], criterios: list[dict], resultados_map: dict) -> dict:
    criteria = [
        {
            "id": criterio["id"],
            "key": f"C{index}",
            "criterio": criterio["descripcion"],
            "capacidad": criterio["capacidad_nombre"],
        }
        for index, criterio in enumerate(criterios, start=1)
    ]

    students = []
    for index, estudiante in enumerate(estudiantes, start=1):
        values = []
        levels = []
        for criterio in criterios:
            resultado = resultados_map.get((estudiante["id"], criterio["id"]))
            nivel = resultado["nivel"] if resultado else None
            values.append(LEVEL_ORDINAL.get(nivel) if nivel else None)
            levels.append(
                {
                    "nivel": nivel,
                    "label": LEVEL_LABELS.get(nivel, "Sin evaluacion") if nivel else "Sin evaluacion",
                }
            )
        students.append(
            {
                "id": estudiante["id"],
                "numero": index,
                "nombre": estudiante["nombre"],
                "values": values,
                "levels": levels,
            }
        )

    return {"criteria": criteria, "students": students}


def build_print_ficha_data(ficha_id: int) -> dict:
    estudiantes = [dict(row) for row in list_estudiantes(ficha_id)]
    criterios = [dict(row) for row in list_criterios(ficha_id)]
    resultados = {
        (row["estudiante_id"], row["criterio_id"]): dict(row)
        for row in list_resultados(ficha_id)
    }

    numbered_students = []
    for index, estudiante in enumerate(estudiantes, start=1):
        item = dict(estudiante)
        item["numero"] = index
        numbered_students.append(item)

    print_criterios = []
    for criterio in criterios:
        raw_rows = [
            resultados.get((estudiante["id"], criterio["id"]))
            for estudiante in numbered_students
        ]
        evidencias = [
            (row.get("evidencia") or "").strip()
            for row in raw_rows
            if row and (row.get("evidencia") or "").strip()
        ]
        unique_evidencias = list(dict.fromkeys(evidencias))
        use_general_evidence = (
            len(unique_evidencias) == 1
            and len(evidencias) == len(numbered_students)
            and len(numbered_students) > 1
        )

        student_rows = []
        for estudiante in numbered_students:
            resultado = resultados.get((estudiante["id"], criterio["id"]))
            student_rows.append(
                {
                    "estudiante_id": estudiante["id"],
                    "numero": estudiante["numero"],
                    "nombre": estudiante["nombre"],
                    "nivel": resultado["nivel"] if resultado else "",
                    "evidencia": "" if use_general_evidence else (resultado["evidencia"] if resultado else ""),
                }
            )

        item = dict(criterio)
        item.update(
            {
                "rowspan": max(len(student_rows), 1),
                "student_rows": student_rows,
                "general_evidence": unique_evidencias[0] if use_general_evidence else "",
            }
        )
        print_criterios.append(item)

    return {
        "estudiantes": numbered_students,
        "criterios": print_criterios,
        "levels": LEVELS,
        "level_labels": LEVEL_LABELS,
        "total_estudiantes": len(numbered_students),
    }


@main_bp.route("/dashboard")
@login_required
def dashboard():
    fichas = list_fichas(current_user)
    return render_template("dashboard.html", fichas=fichas[:6], total_fichas=len(fichas))


def serialize_catalog_row(row):
    return dict(row) if row else {}


def valid_cycle(value: str) -> bool:
    return value in {"I", "II", "I y II"}


def catalog_cycle_matches(item_cycle: str | None, selected_cycle: str) -> bool:
    return selected_cycle == "I y II" or item_cycle in {selected_cycle, "I y II"}


@main_bp.route("/api/areas")
@login_required
def api_areas():
    ciclo = request.args.get("ciclo", "").strip()
    if ciclo and not valid_cycle(ciclo):
        abort(400)
    return jsonify([serialize_catalog_row(row) for row in list_areas(ciclo or None)])


@main_bp.route("/api/competencias/<int:area_id>")
@login_required
def api_competencias(area_id: int):
    if not get_area(area_id):
        abort(404)
    ciclo = request.args.get("ciclo", "").strip()
    if ciclo and not valid_cycle(ciclo):
        abort(400)
    return jsonify([serialize_catalog_row(row) for row in list_competencias(area_id, ciclo or None)])


@main_bp.route("/api/areas/<int:area_id>/competencias")
@login_required
def api_competencias_legacy(area_id: int):
    return api_competencias(area_id)


@main_bp.route("/api/capacidades/<int:competencia_id>")
@login_required
def api_capacidades(competencia_id: int):
    if not get_competencia(competencia_id):
        abort(404)
    return jsonify([serialize_catalog_row(row) for row in list_capacidades(competencia_id)])


@main_bp.route("/api/competencias/<int:competencia_id>/capacidades")
@login_required
def api_capacidades_legacy(competencia_id: int):
    return api_capacidades(competencia_id)


@main_bp.route("/nueva-ficha", methods=["GET", "POST"])
@login_required
def nueva_ficha():
    areas = list_areas()
    if request.method == "POST":
        integrantes = request.form.get("integrantes", "")
        names = split_integrantes(integrantes)
        numero_estudiantes = len(names) or int(request.form.get("numero_estudiantes") or 0)
        ciclo = request.form["ciclo"].strip()
        area_id = int(request.form["area_id"])
        competencia_id = int(request.form["competencia_id"])
        area = get_area(area_id)
        competencia = get_competencia(competencia_id, area_id)
        if (
            not valid_cycle(ciclo)
            or not area
            or not competencia
            or not catalog_cycle_matches(area["ciclo"], ciclo)
            or not catalog_cycle_matches(competencia["ciclo"], ciclo)
        ):
            flash("Selecciona ciclo, area y competencia validos del catalogo CNEB.", "danger")
            return redirect(url_for("main.nueva_ficha"))
        cursor = execute(
            """
            INSERT INTO fichas (
                usuario_id, institucion, docente, fecha, aula_edad, ciclo, area_id, competencia_id,
                actividad, numero_grupo, numero_estudiantes, integrantes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(current_user.id),
                request.form["institucion"].strip(),
                request.form["docente"].strip(),
                request.form["fecha"],
                request.form["aula_edad"].strip(),
                ciclo,
                area_id,
                competencia_id,
                request.form["actividad"].strip(),
                request.form.get("numero_grupo", "").strip(),
                numero_estudiantes,
                integrantes.strip(),
            ),
        )
        ficha_id = cursor.lastrowid
        for index, nombre in enumerate(names, start=1):
            execute(
                "INSERT INTO estudiantes (ficha_id, nombre, orden) VALUES (?, ?, ?)",
                (ficha_id, nombre, index),
            )
        sync_student_count(ficha_id)
        flash("Ficha creada. Ahora registra o confirma los estudiantes.", "success")
        return redirect(url_for("main.estudiantes", ficha_id=ficha_id))

    return render_template("fichas/nueva.html", areas=areas)


@main_bp.route("/fichas")
@login_required
def fichas():
    return render_template("fichas/lista.html", fichas=list_fichas(current_user))


@main_bp.route("/reportes")
@login_required
def reportes():
    return render_template("reportes/lista.html", fichas=list_fichas(current_user))


@main_bp.route("/ficha/<int:ficha_id>/estudiantes", methods=["GET", "POST"])
@login_required
def estudiantes(ficha_id: int):
    ficha = require_ficha(ficha_id)
    if request.method == "POST":
        action = request.form.get("action", "add")
        if action == "add":
            nombre = request.form.get("nombre", "").strip()
            if nombre:
                next_order = len(list_estudiantes(ficha_id)) + 1
                execute(
                    "INSERT INTO estudiantes (ficha_id, nombre, orden) VALUES (?, ?, ?)",
                    (ficha_id, nombre, next_order),
                )
        elif action == "update":
            for key, value in request.form.items():
                if key.startswith("estudiante_"):
                    estudiante_id = int(key.split("_", 1)[1])
                    execute(
                        "UPDATE estudiantes SET nombre = ? WHERE id = ? AND ficha_id = ?",
                        (value.strip(), estudiante_id, ficha_id),
                    )
        elif action == "delete":
            estudiante_id = int(request.form["estudiante_id"])
            execute("DELETE FROM estudiantes WHERE id = ? AND ficha_id = ?", (estudiante_id, ficha_id))
        sync_student_count(ficha_id)
        return redirect(url_for("main.estudiantes", ficha_id=ficha_id))

    return render_template("fichas/estudiantes.html", ficha=ficha, estudiantes=list_estudiantes(ficha_id))


@main_bp.route("/ficha/<int:ficha_id>/criterios", methods=["GET", "POST"])
@login_required
def criterios(ficha_id: int):
    ficha = require_ficha(ficha_id)
    capacidades = list_capacidades(ficha["competencia_id"])
    if request.method == "POST":
        action = request.form.get("action", "add")
        if action == "add":
            descripcion = request.form.get("descripcion", "").strip()
            capacidad_id = int(request.form["capacidad_id"])
            if descripcion:
                if not get_capacidad(capacidad_id, ficha["competencia_id"]):
                    flash("Selecciona una capacidad valida para la competencia de la ficha.", "danger")
                    return redirect(url_for("main.criterios", ficha_id=ficha_id))
                next_order = len(list_criterios(ficha_id)) + 1
                execute(
                    """
                    INSERT INTO criterios (ficha_id, capacidad_id, descripcion, orden)
                    VALUES (?, ?, ?, ?)
                    """,
                    (ficha_id, capacidad_id, descripcion, next_order),
                )
        elif action == "update":
            for key, value in request.form.items():
                if key.startswith("criterio_"):
                    criterio_id = int(key.split("_", 1)[1])
                    capacidad_id = int(request.form.get(f"capacidad_{criterio_id}"))
                    if not get_capacidad(capacidad_id, ficha["competencia_id"]):
                        flash("Uno de los criterios usa una capacidad fuera de la competencia de la ficha.", "danger")
                        return redirect(url_for("main.criterios", ficha_id=ficha_id))
                    execute(
                        """
                        UPDATE criterios
                        SET descripcion = ?, capacidad_id = ?
                        WHERE id = ? AND ficha_id = ?
                        """,
                        (value.strip(), capacidad_id, criterio_id, ficha_id),
                    )
        elif action == "delete":
            criterio_id = int(request.form["criterio_id"])
            execute("DELETE FROM criterios WHERE id = ? AND ficha_id = ?", (criterio_id, ficha_id))
        return redirect(url_for("main.criterios", ficha_id=ficha_id))

    return render_template(
        "fichas/criterios.html",
        ficha=ficha,
        capacidades=capacidades,
        criterios=list_criterios(ficha_id),
    )


@main_bp.route("/ficha/<int:ficha_id>/evaluar", methods=["GET", "POST"])
@login_required
def evaluar(ficha_id: int):
    ficha = require_ficha(ficha_id)
    estudiantes_rows = list_estudiantes(ficha_id)
    criterios_rows = list_criterios(ficha_id)

    if request.method == "POST":
        for estudiante in estudiantes_rows:
            for criterio in criterios_rows:
                key = f"nivel_{estudiante['id']}_{criterio['id']}"
                ev_key = f"evidencia_{estudiante['id']}_{criterio['id']}"
                nivel = request.form.get(key)
                evidencia = request.form.get(ev_key, "").strip()
                if nivel in LEVELS:
                    execute(
                        """
                        INSERT INTO resultados (ficha_id, estudiante_id, criterio_id, nivel, evidencia)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(estudiante_id, criterio_id) DO UPDATE SET
                            nivel = excluded.nivel,
                            evidencia = excluded.evidencia,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (ficha_id, estudiante["id"], criterio["id"], nivel, evidencia),
                    )
        execute(
            """
            UPDATE fichas
            SET observaciones_generales = ?, acciones_pedagogicas = ?
            WHERE id = ?
            """,
            (
                request.form.get("observaciones_generales", "").strip(),
                request.form.get("acciones_pedagogicas", "").strip(),
                ficha_id,
            ),
        )
        flash("Evaluación guardada correctamente.", "success")
        return redirect(url_for("main.resultados", ficha_id=ficha_id))

    existing = {
        f"{row['estudiante_id']}-{row['criterio_id']}": dict(row) for row in list_resultados(ficha_id)
    }
    return render_template(
        "fichas/evaluar.html",
        ficha=ficha,
        estudiantes=estudiantes_rows,
        criterios=criterios_rows,
        resultados=existing,
        levels=LEVELS,
        level_labels=LEVEL_LABELS,
    )


@main_bp.route("/ficha/<int:ficha_id>/resultados", methods=["GET", "POST"])
@login_required
def resultados(ficha_id: int):
    ficha = require_ficha(ficha_id)
    if request.method == "POST":
        execute(
            """
            UPDATE fichas
            SET analisis_interpretacion = ?, acciones_pedagogicas = ?
            WHERE id = ?
            """,
            (
                request.form.get("analisis_interpretacion", "").strip(),
                request.form.get("acciones_pedagogicas", "").strip(),
                ficha_id,
            ),
        )
        flash("Análisis guardado.", "success")
        return redirect(url_for("main.resultados", ficha_id=ficha_id))

    return render_template("fichas/resultados.html", ficha=ficha, stats=build_stats(ficha_id))


@main_bp.route("/ficha/<int:ficha_id>/imprimir-ficha")
@login_required
def imprimir_ficha(ficha_id: int):
    ficha = require_ficha(ficha_id)
    return render_template(
        "print/imprimir_ficha.html",
        ficha=ficha,
        print_data=build_print_ficha_data(ficha_id),
    )


@main_bp.route("/ficha/<int:ficha_id>/imprimir-reporte")
@login_required
def imprimir_reporte(ficha_id: int):
    ficha = require_ficha(ficha_id)
    return render_template("print/imprimir_reporte.html", ficha=ficha, stats=build_stats(ficha_id))


@main_bp.route("/admin/docentes", methods=["GET", "POST"])
@login_required
def admin_docentes():
    if not current_user.is_admin:
        abort(403)
    if request.method == "POST":
        execute(
            """
            INSERT INTO usuarios (nombre, email, password_hash, rol)
            VALUES (?, ?, ?, 'docente')
            """,
            (
                request.form["nombre"].strip(),
                request.form["email"].strip().lower(),
                generate_password_hash(request.form["password"]),
            ),
        )
        flash("Docente creado.", "success")
        return redirect(url_for("main.admin_docentes"))

    docentes = query_all("SELECT * FROM usuarios WHERE rol = 'docente' ORDER BY nombre")
    return render_template("admin/docentes.html", docentes=docentes)


@main_bp.route("/admin/catalogo")
@login_required
def admin_catalogo():
    if not current_user.is_admin:
        abort(403)
    areas = list_areas()
    catalogo = []
    for area in areas:
        competencias = []
        for competencia in list_competencias(area["id"]):
            competencias.append(
                {"competencia": competencia, "capacidades": list_capacidades(competencia["id"])}
            )
        catalogo.append({"area": area, "competencias": competencias})
    return render_template("admin/catalogo.html", catalogo=catalogo)
