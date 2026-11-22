"""Escolha de momentos usando Most Replayed (se houver) ou energia do áudio.

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

    # Prioriza segundos que comportam uma cena longa, sem começar antes do vídeo.
    candidates = []
    stride = 3 if duration > 180 else 1
    for t in range(0, seconds, stride):
        start = clamp(t - span * .36, 0, max(0, duration - span))
        if duration>180 and start<min(45,duration*.03):
            continue
        # Prefer low-energy boundaries near the candidate, retaining 30–60s.
        if energies:
            lo=max(0,int(start)-3); hi=min(len(energies),int(start)+4)
            if hi>lo: start=float(min(range(lo,hi),key=lambda i:energies[i]))
            start=min(start,duration-span)
        start = round(start, 2)
        if duration>180 and start+span>duration-30:
            continue
        # Verifica pontuação ao redor do pico e duração útil para evitar trechos vazios.
        center = int(min(seconds - 1, start + span / 2))
        window = scores[max(0, center - 7):min(seconds, center + 8)]
        value = sum(window) / max(1, len(window))
        candidates.append((value, start))
    candidates.sort(reverse=True)
    results = []
    min_gap = max(span * 1.2, min(110, duration / max(3, count * 2)))
    for score, start in candidates:
        if all(abs(start - s.start) >= min_gap for s in results):
            results.append(Segment(start, round(start + span, 2), round(score, 4), reason))
        if len(results) == count:
            break
    if len(results) < count:
        # Vídeos menores podem não ter espaço para vários cortes totalmente distintos.
        for i in range(count * 4):
            start = clamp((duration - span) * (i + .5) / (count * 4), 0, duration - span)
            if duration>180 and (start<min(45,duration*.03) or start+span>duration-30):
                continue
            if all(abs(start - s.start) >= span for s in results):
                results.append(Segment(round(start, 2), round(start + span, 2), 0.1, reason))
            if len(results) == count:
                break
    return sorted(results, key=lambda s: s.start)
