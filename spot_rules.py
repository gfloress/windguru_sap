"""Regras pessoais do Classico/Madeirol. Preencher incrementalmente."""
from rules_engine import Metrics, Verdict

# Defina em km/h antes de ativar as regras. Igual ao limiar ja e relevante.
WIND_RELEVANT_KMH = None


def classify(metrics: Metrics) -> Verdict | None:
    # Direcao chega como None quando vento fraco: nao penalize essa ausencia.
    # Verifique None nos campos de onda/swell usados pela sua formula.
    # Retorne Verdict("Está bom", "Motivo") ou None se nao houver regra/dados.
    return None
