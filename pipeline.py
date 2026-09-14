"""Avalia a hora atual do ultimo lote; envia somente mudancas confirmadas."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import os
import sqlite3
from rules_engine import Metrics, classify
from notifiers import Pushover


def notify_changed(conn, spot, verdict, forecast_time, notifier):
    conn.execute("""CREATE TABLE IF NOT EXISTS ultimo_estado_notificado (
        spot TEXT PRIMARY KEY, classificacao TEXT NOT NULL,
        horario_previsto TEXT NOT NULL, notificado_em TEXT NOT NULL
    )""")
    conn.commit()
    # Serializa leitura/envio/escrita entre processos usando o MESMO SQLite.
    conn.execute("BEGIN IMMEDIATE")
    try:
        previous = conn.execute(
            "SELECT classificacao FROM ultimo_estado_notificado WHERE spot=?", (spot,)
        ).fetchone()
        if previous and previous[0] == verdict.classification:
            conn.rollback()
            return False
        notifier.send("Windguru SAP · Clássico/Madeirol",
                      f"{verdict.classification}\nPrevisão: {forecast_time} (Barra da Tijuca)"
                      f"\n{verdict.reason}\nDados: Open-Meteo")
        conn.execute("""INSERT INTO ultimo_estado_notificado VALUES (?, ?, ?, ?)
            ON CONFLICT(spot) DO UPDATE SET classificacao=excluded.classificacao,
            horario_previsto=excluded.horario_previsto,
            notificado_em=excluded.notificado_em""",
            (spot, verdict.classification, forecast_time, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise


def evaluate_latest(conn, spot, local_timezone, *, now=None, notifier=None,
                    plugin=None, dry_run=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now precisa ter timezone")
    hour = now.astimezone(ZoneInfo(local_timezone)).replace(minute=0, second=0, microsecond=0)
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    row = cursor.execute("""SELECT * FROM previsoes_brutas WHERE spot=?
        AND coletado_em=(SELECT MAX(coletado_em) FROM previsoes_brutas WHERE spot=?)
        AND horario_previsto=? ORDER BY id DESC LIMIT 1""",
        (spot, spot, hour.strftime("%Y-%m-%dT%H:%M"))).fetchone()
    if row is None:
        raise ValueError("Ultimo lote nao contem previsao para a hora atual")
    age = now - datetime.fromisoformat(row["coletado_em"])
    if not timedelta(minutes=-5) <= age <= timedelta(hours=3):
        raise ValueError("Coleta antiga ou com horario invalido; notificacao suspensa")
    verdict = classify(Metrics(**{name: row[name] for name in Metrics.__dataclass_fields__}),
                       plugin or os.environ.get("SAP_RULES_MODULE", "spot_rules"))
    if verdict is None:
        print("Sem veredicto: regras pendentes ou dados insuficientes. Estado preservado.")
        return None
    if dry_run is None:
        dry_run = os.environ.get("SAP_DRY_RUN", "1") != "0"
    if dry_run:
        print(f"Simulacao: {verdict.classification} — {verdict.reason}")
        return False
    sent = notify_changed(conn, spot, verdict, row["horario_previsto"], notifier or Pushover())
    print("Notificacao aceita pelo Pushover." if sent else "Classificacao inalterada.")
    return sent
