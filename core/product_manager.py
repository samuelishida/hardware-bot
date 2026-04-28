"""
core/product_manager.py — Gerenciador de produtos dinâmicos.

Permite buscar e monitorar qualquer produto, não apenas hardcoded.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional
from config import STORE_URL_TEMPLATES, STORE_COLORS, STORE_DISPLAY_NAMES


@dataclass
class ProductSearch:
    """Representa um produto sendo buscado."""
    name: str
    search_term: str


class ProductManager:
    """Gerencia buscas de produtos dinâmicos."""
    
    @staticmethod
    def normalize_search_term(term: str) -> str:
        """
        Normaliza termo de busca para URLs.
        
        Exemplos:
          "RTX 4060 Ti" → "rtx-4060-ti"
          "Ryzen 5 5700X3D" → "ryzen-5-5700x3d"
        """
        term = re.sub(r'[^\w\s-]', '', term)
        term = term.lower().strip()
        term = re.sub(r'[-\s]+', '-', term)
        return term
    
    @staticmethod
    def parse_product_name(user_input: str) -> ProductSearch:
        """
        Parse entrada do usuário para extrair nome do produto.
        """
        name = user_input.strip()
        search_term = ProductManager.normalize_search_term(name)
        return ProductSearch(name=name, search_term=search_term)
    
    @staticmethod
    def get_search_url(store_id: str, search_term: str) -> str:
        """
        Gera URL de busca para uma loja específica.
        """
        template = STORE_URL_TEMPLATES.get(store_id)
        if not template:
            raise ValueError(f"Loja '{store_id}' não suportada")
        return template.format(query=search_term)
    
    @staticmethod
    def get_all_search_urls(search_term: str) -> dict[str, str]:
        """
        Gera URLs de busca para todas as lojas.
        """
        return {
            store_id: template.format(query=search_term)
            for store_id, template in STORE_URL_TEMPLATES.items()
        }
    
    @staticmethod
    def format_price_brl(price: Optional[float]) -> str:
        """Formata preço em BRL."""
        if price is None:
            return "Indisponível"
        return f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    @staticmethod
    def get_store_colors() -> dict[str, int]:
        """Retorna cores das lojas para embeds."""
        return STORE_COLORS
    
    @staticmethod
    def get_store_display_names() -> dict[str, str]:
        """Retorna nomes amigáveis das lojas."""
        return STORE_DISPLAY_NAMES
