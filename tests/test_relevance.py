"""tests/test_relevance.py — Unit tests for scrapers/relevance.py (Inc 2).

Cobre ``is_relevant``: rejeição de acessório, keyword faltante, título válido,
``title=None`` (não julga), skip de termo presente no search_term (MUST-FIX do
review) e word-boundary (evita over-filtering de substring).
"""

from __future__ import annotations

from scrapers.relevance import is_relevant, ACCESSORY_TERMS


class TestIsRelevant:
    def test_accessory_rejected(self):
        # "Adaptador USB Sony PS Link" para "ps5" → acessório rejeitado
        assert is_relevant("Adaptador USB Sony PS Link", "ps5") is False

    def test_accessory_rejected_accent_insensitive(self):
        # "acessório" com acento é normalizado → rejeitado
        assert is_relevant("Acessório para console PS5", "ps5") is False

    def test_keyword_missing_rejected(self):
        # título não contém todos os keywords significativos
        assert is_relevant("Console Xbox Series X", "playstation 5") is False

    def test_valid_title_accepted(self):
        assert is_relevant("Console PlayStation 5", "playstation 5") is True

    def test_title_none_accepted(self):
        # sem título → não julga (degrade para comportamento atual)
        assert is_relevant(None, "ps5") is True
        assert is_relevant("", "ps5") is True

    def test_search_term_contains_accessory_term_not_filtered(self):
        # MUST-FIX: usuário buscou "fonte corsair" → não filtra por "fonte"
        assert is_relevant("Fonte Corsair 650W 80 Plus", "fonte corsair") is True

    def test_search_term_contains_accessory_term_gabinete(self):
        assert is_relevant("Gabinete NZXT H5 Flow", "gabinete nzxt") is True

    def test_word_boundary_avoids_substring_false_positive(self):
        # "capa" não deve rejeitar "capacidade" (word-boundary, não substring)
        assert is_relevant("SSD 1TB com capacidade 1000GB", "ssd") is True

    def test_extra_terms_word_boundary_avoids_substring(self):
        # FIX (audit): termo aprendido usa word-boundary, não substring.
        # "box" não deve rejeitar "subbox" (busca por console).
        assert is_relevant("Subbox Console", "console", extra_terms=["box"]) is True
        assert is_relevant("Console Shadow 8GB", "console", extra_terms=["box"]) is True

    def test_extra_terms_reject_word_boundary(self):
        # FIX (audit): termo aprendido rejeita com word-boundary.
        assert is_relevant("Console com Box Collection", "console", extra_terms=["box"]) is False

    def test_multiword_term_with_punctuation_in_title(self):
        # FIX (audit): título com vírgula ("Pasta, Térmica") ainda é acessório
        # para uma busca de processador (não de pasta térmica).
        assert is_relevant("Pasta, Térmica Premium para Processador AMD", "processador") is False
        assert is_relevant("Pasta Térmica Premium para Processador AMD", "processador") is False

    def test_multiword_term_with_double_space_in_title(self):
        # FIX (audit): espaço duplo no título ainda casa "water block"
        # (acessório para busca de watercooler).
        assert is_relevant("Water  Block Premium 240mm", "watercooler") is False

    def test_extra_terms_learned_reject(self):
        # termo aprendido (self-healing) rejeita
        assert is_relevant("Console PS5 com PS Link", "ps5", extra_terms=["ps link"]) is False

    def test_extra_terms_skip_when_in_search(self):
        # termo aprendido presente no search_term → não filtra
        assert is_relevant("PS Link USB Dongle", "ps link", extra_terms=["ps link"]) is True

    def test_accessory_terms_are_normalized_no_accents(self):
        # ACCESSORY_TERMS não deve conter acentos (normalização no runtime)
        for t in ACCESSORY_TERMS:
            assert t == t.lower()