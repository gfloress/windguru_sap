"""
Windguru SAP - Coletor de dados
---------------------------------
Busca previsao de vento (Forecast API) e de ondas/swell (Marine API) do
Open-Meteo para um unico pico (Barra da Tijuca - Classico/Madeirol) e
grava tudo em um banco SQLite local.

Por que duas chamadas de API?
A Marine API do Open-Meteo tras ondas/swell, mas NAO tras vento.
O vento vem da Forecast API "normal". Juntamos as duas pelo horario.

Por que guardar "coletado_em" junto com "horario_previsto"?
Cada vez que rodamos o script, pegamos a previsao mais recente para as
proximas horas. Guardando quando cada previsao foi coletada, criamos um
historico de como a previsao para um mesmo horario foi mudando com o
tempo - isso e util mais pra frente pra validar o motor de regras contra
o que realmente aconteceu.

Como rodar:
    pip install -r requirements.txt
    python collector.py
"""

import os
import sqlite3
import requests
from datetime import datetime, timezone

# ---------------------------------------------------------------------
# Configuracao do pico. Ajuste as coordenadas se souber o ponto exato.
# ---------------------------------------------------------------------
SPOT_NAME = "barra_da_tijuca_classico_madeirol"
LATITUDE = -23.01
LONGITUDE = -43.365
TIMEZONE = "America/Sao_Paulo"
FORECAST_HOURS = 72
DB_PATH = os.environ.get("SAP_DB_PATH", "windguru_sap.db")

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_marine_data():
    """Busca altura/periodo/direcao de onda e de swell."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join([
            "wave_height", "wave_direction", "wave_period",
            "swell_wave_height", "swell_wave_direction", "swell_wave_period",
        ]),
        "timezone": TIMEZONE,
        "forecast_hours": FORECAST_HOURS,
        "models": "best_match",
    }
    resp = requests.get(MARINE_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()["hourly"]


def fetch_wind_data():
    """Busca velocidade, rajada e direcao do vento."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "wind_speed_unit": "kmh",
        "timezone": TIMEZONE,
        "forecast_hours": FORECAST_HOURS,
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()["hourly"]


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS previsoes_brutas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spot TEXT NOT NULL,
            coletado_em TEXT NOT NULL,
            horario_previsto TEXT NOT NULL,
            vento_velocidade_kmh REAL,
            vento_rajada_kmh REAL,
            vento_direcao_graus REAL,
            onda_altura_m REAL,
            onda_periodo_s REAL,
            onda_direcao_graus REAL,
            swell_altura_m REAL,
            swell_periodo_s REAL,
            swell_direcao_graus REAL,
            UNIQUE(spot, horario_previsto, coletado_em)
        )
    """)
    conn.commit()


def merge_and_save(conn, marine, wind):
    coletado_em = datetime.now(timezone.utc).isoformat()

    # Validar antes de gravar; nunca associar horarios diferentes por indice.
    for data in (marine, wind):
        if not data["time"] or len(set(data["time"])) != len(data["time"]):
            raise ValueError("Horarios vazios ou duplicados na API")
        if any(len(values) != len(data["time"]) for values in data.values()):
            raise ValueError("Vetores horarios inconsistentes na API")
    if set(marine["time"]) != set(wind["time"]):
        raise ValueError("Marine e Forecast retornaram horarios diferentes; tentar novamente")
    wind_index = {time: i for i, time in enumerate(wind["time"])}
    horarios = marine["time"]
    rows = []
    for i, horario in enumerate(horarios):
        j = wind_index[horario]
        rows.append((
            SPOT_NAME,
            coletado_em,
            horario,
            wind["wind_speed_10m"][j],
            wind["wind_gusts_10m"][j],
            wind["wind_direction_10m"][j],
            marine["wave_height"][i],
            marine["wave_period"][i],
            marine["wave_direction"][i],
            marine["swell_wave_height"][i],
            marine["swell_wave_period"][i],
            marine["swell_wave_direction"][i],
        ))

    conn.executemany("""
        INSERT OR IGNORE INTO previsoes_brutas (
            spot, coletado_em, horario_previsto,
            vento_velocidade_kmh, vento_rajada_kmh, vento_direcao_graus,
            onda_altura_m, onda_periodo_s, onda_direcao_graus,
            swell_altura_m, swell_periodo_s, swell_direcao_graus
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return len(rows)


def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    print(f"Buscando dados de onda/swell para {SPOT_NAME}...")
    marine = fetch_marine_data()

    print("Buscando dados de vento...")
    wind = fetch_wind_data()

    total = merge_and_save(conn, marine, wind)
    print(f"OK - {total} horas de previsao gravadas em {DB_PATH}")

    from pipeline import evaluate_latest
    evaluate_latest(conn, SPOT_NAME, TIMEZONE)

    conn.close()


if __name__ == "__main__":
    main()
