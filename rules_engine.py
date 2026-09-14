"""Contrato do plugin: classify(Metrics) -> Verdict | None. Unidades explicitas."""
from dataclasses import dataclass, replace
from importlib import import_module
import math


@dataclass(frozen=True)
class Metrics:
    vento_velocidade_kmh: float | None
    vento_rajada_kmh: float | None
    vento_direcao_graus: float | None
    onda_altura_m: float | None
    onda_periodo_s: float | None
    onda_direcao_graus: float | None
    swell_altura_m: float | None
    swell_periodo_s: float | None
    swell_direcao_graus: float | None


@dataclass(frozen=True)
class Verdict:
    classification: str
    reason: str = ""


def classify(metrics, plugin="spot_rules"):
    module = import_module(plugin)
    threshold = module.WIND_RELEVANT_KMH
    # Nao inventar o limiar que o surfista ainda vai definir.
    if threshold is None:
        return None
    if not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("WIND_RELEVANT_KMH deve ser positivo e finito")
    cleaned = {}
    for name, value in vars(metrics).items():
        if value is not None and (not isinstance(value, (int, float)) or
                                  not math.isfinite(value) or value < 0 or
                                  (name.endswith("graus") and value > 360)):
            value = None
        cleaned[name] = value
    metrics = Metrics(**cleaned)
    speed = metrics.vento_velocidade_kmh
    if speed is None:
        return None
    if speed < threshold:
        metrics = replace(metrics, vento_direcao_graus=None)
    elif metrics.vento_direcao_graus is None:
        return None
    result = module.classify(metrics)
    if result is not None and (not isinstance(result, Verdict) or
                              not result.classification.strip() or
                              len(result.classification) > 100 or len(result.reason) > 500):
        raise ValueError("Plugin deve retornar Verdict valido ou None")
    return result
