"""Escolha de momentos por intensidade, continuidade e diversidade temporal.

Heurísticas não representam dados reais de audiência.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    score: float
    reason: str

    @property
    def length(self):
        return round(self.end - self.start, 3)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def extract_heatmap(metadata: dict) -> list[tuple[float, float, float]]:
    """O yt-dlp pode retornar uma lista 'heatmap' do YouTube (não é garantido)."""
    result = []
    for p in (metadata.get('heatmap') or []):
        try:
            a = float(p.get('start_time', 0))
            b = float(p.get('end_time', 0))
            v = float(p.get('value', 0))
            if math.isfinite(v) and v > 0 and 0 <= a < b and math.isfinite(b):
                result.append((a, b, clamp(v, 0, 1)))
        except (ValueError, TypeError, AttributeError):
            continue
    return result


def _smoothed(values: Sequence[float], radius: int):
    """Média móvel O(n), sem depender de NumPy para testes."""
    if not values:
        return []
    radius = max(1, radius)
    prefix = [0.0]
    for v in values:
        prefix.append(prefix[-1] + float(v))
    out = []
    for i in range(len(values)):
        a, b = max(0, i - radius), min(len(values), i + radius + 1)
        out.append((prefix[b] - prefix[a]) / (b - a))
    return out


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    ordered = sorted(values)
    lo = ordered[int((len(ordered) - 1) * .08)]
    hi = ordered[int((len(ordered) - 1) * .98)]
    if hi - lo < 1e-8:
        return [.25] * len(values)
    return [clamp((v - lo) / (hi - lo), 0, 1) for v in values]


def pick_segments(
    duration: float,
    count: int = 5,
    clip_seconds: int = 45,
    heatmap: list[tuple[float, float, float]] | None = None,
    energies: Sequence[float] | None = None,
) -> list[Segment]:
    """Tenta distanciar os cortes e prioriza picos de audiência (ou energia).

    'energies' contém uma medição por segundo de áudio; heatmap tem preferência.
    """
    if not math.isfinite(duration) or duration < 30 or duration>12*3600:
        raise ValueError('O vídeo original precisa ter pelo menos 30 segundos.')
    count = max(1, min(50, int(count)))
    span = max(30, min(int(clip_seconds), 60, int(duration)))
    seconds = max(1, math.ceil(duration))
    hm = [0.0] * seconds
    for a, b, strength in (heatmap or []):
        for s in range(max(0, int(a)), min(seconds, math.ceil(b))):
            hm[s] = max(hm[s], strength)
    has_replay = bool(heatmap and any(hm))
    if has_replay:
        scores = _smoothed(hm, max(4, span // 3))
        reason = 'Pico do gráfico Mais reproduzido do YouTube'
    elif energies:
        e = list(float(x) for x in energies[:seconds])
        if len(e) < seconds:
            e.extend([0.0] * (seconds - len(e)))
        # Nível geral + momentos com variação brusca (reações, gritos, etc.).
        smooth = _smoothed(e, 4)
        slow = _smoothed(e, 35)
        novelty = [max(0., a - b) for a, b in zip(smooth, slow)]
        n1 = _normalize(_smoothed(e, max(3, span // 5)))
        n2 = _normalize(_smoothed(novelty, max(2, span // 7)))
        scores = [.48 * a + .52 * b for a, b in zip(n1, n2)]
        reason = 'Heurística de energia e variação do áudio (não é Most Replayed)'
    else:
        scores = [.5] * seconds
        reason = 'Distribuição pelo vídeo (dados de replay e áudio indisponíveis)'

    # Avalia a JANELA COMPLETA, e não apenas 15 segundos do meio. Isso
    # reduz cenas com um grito isolado e 40s sem contexto.
    candidates = []
    stride = 3 if duration > 180 else 1
    normalized_energy = _normalize(list(float(x) for x in energies)) if energies else []
    for t in range(0, seconds, stride):
        start = clamp(t - span * .36, 0, max(0, duration - span))
        if duration > 180 and start < min(45, duration * .03):
            continue
        if energies:
            # Evita cortar no meio de uma reação/fala quando houver pausa próxima.
            lo = max(0, int(start) - 5)
            hi = min(len(energies), int(start) + 6)
            if hi > lo:
                start = float(min(range(lo, hi), key=lambda i: energies[i]))
            start = min(start, duration - span)
        start = round(start, 2)
        if duration > 180 and start + span > duration - 30:
            continue
        lo, hi = int(start), min(seconds, math.ceil(start + span))
        values = scores[lo:hi]
        if not values:
            continue
        ordered = sorted(values, reverse=True)
        top = ordered[:max(1, len(ordered) // 4)]
        # Mistura continuidade do momento com picos reais de interesse.
        value = .72 * (sum(values) / len(values)) + .28 * (sum(top) / len(top))
        if normalized_energy:
            a = min(len(normalized_energy) - 1, lo)
            b = min(len(normalized_energy) - 1, max(lo, hi - 1))
            # Penaliza inícios/fins muito barulhentos (frequente corte de frase).
            boundary = (normalized_energy[a] + normalized_energy[b]) / 2
            value -= .08 * boundary
            if sum(normalized_energy[lo:hi]) / max(1, hi - lo) < .08:
                value -= .12  # pouco conteúdo audível ao longo do corte
        candidates.append((value, start))
    candidates.sort(reverse=True)
    results = []
    min_gap = max(span * 1.2, min(110, duration / max(3, count * 2)))
    while candidates and len(results) < count:
        # Pequeno bônus por diversidade temporal: evita cinco Shorts de um
        # único minuto de um vídeo com várias horas.
        def choice(c):
            score, start = c
            if not results:
                return score
            nearest = min(abs(start - s.start) for s in results)
            diversity = min(1.0, nearest / max(span * 2, duration / max(2, count * 2)))
            return score + .10 * diversity
        best = max(candidates, key=choice)
        candidates.remove(best)
        score, start = best
        if all(abs(start - s.start) >= min_gap for s in results):
            results.append(Segment(start, round(start + span, 2), round(score, 4), reason))
    if len(results) < count:
        # Não duplica intervalos em vídeos pequenos.
        for i in range(count * 4):
            start = clamp((duration - span) * (i + .5) / (count * 4), 0, duration - span)
            if duration > 180 and (start < min(45, duration * .03) or start + span > duration - 30):
                continue
            if all(start + span <= s.start or start >= s.end for s in results):
                results.append(Segment(round(start, 2), round(start + span, 2), 0.1, reason))
            if len(results) == count:
                break
    return sorted(results, key=lambda s: s.start)
