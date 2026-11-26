"""
PostgreSQL repository for predictions, pending audits and accumulated statistics.

The module degrades gracefully: when DATABASE_URL is empty or psycopg2 is not
available, public functions return empty/zero results and log a warning.
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover - dependency is optional at runtime
    psycopg2 = None
    RealDictCursor = None

from parley.config import DATABASE_URL
from parley.models.strategy import clasificar_riesgo

log = logging.getLogger("parley.db")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    fecha DATE NOT NULL,
    fixture_id VARCHAR NOT NULL,
    liga VARCHAR,
    partido VARCHAR,
    mercado VARCHAR NOT NULL,
    seleccion VARCHAR NOT NULL,
    probabilidad NUMERIC,
    cuota NUMERIC,
    ev NUMERIC,
    tier VARCHAR,
    estado VARCHAR DEFAULT 'PENDIENTE',
    resultado_real VARCHAR,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT predictions_unique UNIQUE (fecha, fixture_id, mercado, seleccion)
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_predictions_estado_fecha
    ON predictions (estado, fecha);
"""

VALID_ESTADOS = ("GANADA", "PERDIDA", "NULA")


def _database_url(database_url: Optional[str] = None) -> str:
    return database_url if database_url is not None else DATABASE_URL


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _connect(database_url: Optional[str] = None):
    url = _database_url(database_url)
    if not url:
        return None
    if psycopg2 is None:
        log.error("psycopg2 no está instalado; se omite PostgreSQL.")
        return None
    return psycopg2.connect(url, connect_timeout=10)


def ensure_schema(conn) -> None:
    """Create tables and indexes if they do not exist."""
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
        cur.execute(CREATE_INDEX_SQL)
    conn.commit()


def save_predictions(picks: List[Dict[str, Any]], fecha: Any, database_url: Optional[str] = None) -> int:
    """Persist morning picks. Duplicate (fecha, fixture, market, selection) rows are ignored."""
    if not picks:
        return 0

    conn = _connect(database_url)
    if conn is None:
        log.info("DATABASE_URL no configurada; se omiten %d predicciones.", len(picks))
        return 0

    fecha_val = _as_date(fecha)
    inserted = 0
    try:
        ensure_schema(conn)
        with conn.cursor() as cur:
            for pick in picks:
                fixture_id = str(pick.get("fixture_id") or pick.get("id") or "")
                if not fixture_id:
                    continue

                cuota = pick.get("cuota_real")
                if cuota is None:
                    cuota = pick.get("cuota_justa")
                tier = pick.get("tier") or clasificar_riesgo(pick.get("prob", 0)) or "arriesgado"

                cur.execute(
                    """
                    INSERT INTO predictions
                        (fecha, fixture_id, liga, partido, mercado, seleccion,
                         probabilidad, cuota, ev, tier)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (fecha, fixture_id, mercado, seleccion) DO NOTHING
                    """,
                    (
                        fecha_val,
                        fixture_id,
                        pick.get("liga"),
                        pick.get("partido"),
                        pick.get("mercado"),
                        pick.get("seleccion"),
                        pick.get("prob"),
                        cuota,
                        pick.get("ev"),
                        tier,
                    ),
                )
                inserted += cur.rowcount
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log.error("Error guardando predicciones: %s", type(exc).__name__)
        return 0
    finally:
        conn.close()

    log.info("Predicciones guardadas: %d nuevas de %d", inserted, len(picks))
    return inserted


def get_pending_predictions(hasta: Any = None, database_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return PENDIENTE predictions for today or earlier."""
    conn = _connect(database_url)
    if conn is None:
        return []

    hasta_val = _as_date(hasta) if hasta is not None else date.today()
    try:
        ensure_schema(conn)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, fecha, fixture_id, liga, partido, mercado, seleccion,
                       probabilidad, cuota, ev, tier, estado, resultado_real, created_at
                FROM predictions
                WHERE estado = 'PENDIENTE' AND fecha <= %s
                ORDER BY fecha, id
                """,
                (hasta_val,),
            )
            return [dict(row) for row in cur.fetchall()]
    except Exception as exc:
        conn.rollback()
        log.error("Error leyendo predicciones pendientes: %s", type(exc).__name__)
        return []
    finally:
        conn.close()


def update_prediction(prediction_id: Any, estado: str, resultado_real: str, database_url: Optional[str] = None) -> bool:
    """Update a prediction result. Returns True when a row was updated."""
    if estado not in VALID_ESTADOS:
        raise ValueError(f"Estado inválido: {estado}")

    conn = _connect(database_url)
    if conn is None:
        return False

    try:
        ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE predictions
                SET estado = %s, resultado_real = %s
                WHERE id = %s
                """,
                (estado, resultado_real, prediction_id),
            )
            updated = cur.rowcount
        conn.commit()
        return updated > 0
    except Exception as exc:
        conn.rollback()
        log.error("Error actualizando predicción %s: %s", prediction_id, type(exc).__name__)
        return False
    finally:
        conn.close()


def calcular_stats(predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute hit rate and flat-stake ROI from resolved predictions.

    NULA rows are excluded from the resolved denominator. Each GANADA adds
    (cuota - 1) units; each PERDIDA subtracts 1 unit.
    """
    ganadas = perdidas = nulas = 0
    ganancia = 0.0

    for row in predictions:
        estado = (row.get("estado") or "").upper()
        if estado == "NULA":
            nulas += 1
            continue
        if estado not in ("GANADA", "PERDIDA"):
            continue

        try:
            cuota = float(row.get("cuota")) if row.get("cuota") is not None else 1.0
        except (TypeError, ValueError):
            cuota = 1.0

        if estado == "GANADA":
            ganadas += 1
            ganancia += cuota - 1.0
        else:
            perdidas += 1
            ganancia -= 1.0

    resueltas = ganadas + perdidas
    return {
        "total": resueltas,
        "ganadas": ganadas,
        "perdidas": perdidas,
        "nulas": nulas,
        "acierto_pct": (ganadas / resueltas * 100.0) if resueltas else 0.0,
        "roi_pct": (ganancia / resueltas * 100.0) if resueltas else 0.0,
        "ganancia": ganancia,
    }


def get_stats(database_url: Optional[str] = None) -> Dict[str, Any]:
    """Return accumulated statistics over all resolved predictions."""
    conn = _connect(database_url)
    if conn is None:
        return calcular_stats([])

    try:
        ensure_schema(conn)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT estado, cuota
                FROM predictions
                WHERE estado IN ('GANADA', 'PERDIDA', 'NULA')
                """
            )
            rows = [dict(row) for row in cur.fetchall()]
        return calcular_stats(rows)
    except Exception as exc:
        conn.rollback()
        log.error("Error calculando estadísticas: %s", type(exc).__name__)
        return calcular_stats([])
    finally:
        conn.close()
