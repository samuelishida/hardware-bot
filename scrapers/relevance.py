"""scrapers/relevance.py — Filtro de relevância compartilhado.

Rejeita acessórios/irrelevantes de forma determinística na origem (scraper) e
serve de rede de segurança para o gate do Analista (Inc 4).

Regras (ordem de avaliação):
  1. ``title`` vazio/None → ``True`` (não julga; degrada para o comportamento atual).
  2. Todos os keywords significativos (len>=2) de ``search_term`` devem estar em
     ``title`` (rede de segurança; redundante com o pré-filtro JS dos scrapers).
  3. Nenhum termo de acessório (``ACCESSORY_TERMS`` + ``extra_terms``) pode aparecer
     em ``title`` — **exceto** se o próprio ``search_term`` contiver o termo (o
     usuário buscou explicitamente por ele, ex.: "fonte corsair", "gabinete nzxt").

A checagem de acessório usa **word boundary** (``\\bterm\\b``), não substring, para
evitar falso-positivo de over-filtering (ex.: "capa" não rejeita "capacidade").
"""

from __future__ import annotations

import re
import unicodedata

# Termos de acessório consolidados (baseline em código, compartilhado por todas as
# lojas). Sem acentos — ``_normalize`` remove diacríticos antes de comparar.
ACCESSORY_TERMS = [
    "adaptador", "cabo", "acessorio", "suporte", "base", "cooler",
    "ventoinha", "dissipador", "pasta termica", "conector", "bracket",
    "protetor", "capa", "riser", "extensao", "extensor", "water block",
    "waterblock", "backplate", "fonte", "gabinete", "pastilha",
    "compativel com", "para hdmi", "cabo displayport", "cabo dp",
    "cabo hdmi", "fibra otica", "modulo de interface", "case para",
    "bloco de agua", "placa traseira", "terminal termico",
]

def _term_regex(term: str) -> re.Pattern:
    """Regex de word-boundary; palavras multi-word casam com qualquer whitespace."""
    return re.compile(r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b")


_TERM_RES = {t: _term_regex(t) for t in ACCESSORY_TERMS}


def _normalize(s: str) -> str:
    """Lowercase, remove diacríticos e colapsa pontuação/whitespace em espaço simples.

    ``"Pasta, Térmica Premium"`` → ``"pasta termica premium"`` — permite que termos
    multi-word (``pasta termica``) casem mesmo com vírgula/espaço duplo no título.
    """
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def is_relevant(title: str | None, search_term: str, extra_terms: list[str] | None = None) -> bool:
    """True se o título é relevante para a busca; False se é acessório/irrelevante.

    ``extra_terms`` são termos aprendidos por store (``relevance_overrides``).
    """
    if not title:
        return True  # não julga

    title_norm = _normalize(title)
    search_norm = _normalize(search_term or "")

    # 2. keyword check (rede de segurança; redundante com o pré-filtro JS)
    keywords = [kw for kw in search_norm.split() if len(kw) >= 2]
    match_kws = keywords if keywords else search_norm.split()
    if match_kws and not all(kw in title_norm for kw in match_kws):
        return False

    # 3. accessory term check — pula termos que o usuário buscou explicitamente.
    #    Todos os termos (baseline + aprendidos) usam word-boundary (``\b...\b``),
    #    para não rejeitar por substring (ex.: 'capa' não rejeita 'capacidade').
    terms = list(ACCESSORY_TERMS)
    if extra_terms:
        terms.extend(_normalize(t) for t in extra_terms)

    for term in terms:
        if term in search_norm:
            continue  # usuário buscou por esse termo → não filtra
        res = _TERM_RES.get(term)
        if res is None:
            res = _term_regex(term)
        if res.search(title_norm):
            return False
    return True


__all__ = ["is_relevant", "ACCESSORY_TERMS"]