# PreçoBot - Script de Inicialização Rápida
# Uso: .\start-bot.ps1

$Banner = @"
========================================
PrecoBot - Iniciando...
========================================

"@
Write-Host $Banner -ForegroundColor Cyan

# Verifica ambiente virtual
$PYTHON = "e:\Code\.venv\Scripts\python.exe"
if (!(Test-Path $PYTHON)) {
    Write-Host "❌ Erro: Ambiente virtual não encontrado em e:\Code\.venv" -ForegroundColor Red
    Write-Host "Crie com: python -m venv e:\Code\.venv" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Python: $PYTHON" -ForegroundColor Green

# Verifica .env
if (!(Test-Path ".env")) {
    Write-Host "❌ Erro: Arquivo .env não encontrado!" -ForegroundColor Red
    Write-Host "Copie .env.example para .env e configure:" -ForegroundColor Yellow
    Write-Host "  cp .env.example .env" -ForegroundColor Gray
    exit 1
}

Write-Host "✅ .env: Configurado" -ForegroundColor Green

# Verifica dependências
Write-Host "`n📦 Verificando dependências..." -ForegroundColor Cyan
try {
    & $PYTHON -c "import discord, playwright, aiosqlite, apscheduler" 2>$null
    Write-Host "✅ Dependências: OK" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Dependências faltando. Instalando..." -ForegroundColor Yellow
    & $PYTHON -m pip install -r requirements.txt --quiet
    Write-Host "✅ Dependências instaladas" -ForegroundColor Green
}

# Verifica Chromium
Write-Host "`n🌐 Verificando Chromium (Playwright)..." -ForegroundColor Cyan
try {
    & $PYTHON -m playwright install chromium 2>&1 | Out-Null
    Write-Host "✅ Chromium: OK" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Instalando Chromium..." -ForegroundColor Yellow
    & $PYTHON -m playwright install chromium
    Write-Host "✅ Chromium instalado" -ForegroundColor Green
}

# Verifica banco de dados
Write-Host "`n💾 Verificando banco de dados..." -ForegroundColor Cyan
try {
    & $PYTHON -c "from db.database import init_db; import asyncio; asyncio.run(init_db())" 2>$null
    Write-Host "✅ Banco de dados: OK" -ForegroundColor Green
} catch {
    Write-Host "❌ Erro ao inicializar banco de dados" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# Menu de opções
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Escolha uma opção:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. 🚀 Iniciar bot (normal)"
Write-Host "2. 🧪 Executar testes de diagnóstico"
Write-Host "3. 📊 Testar apenas scrapers"
Write-Host "4. 🌐 Testar apenas sites"
Write-Host "5. ⚙️  Verificar configuração"
Write-Host "6. ❌ Sair"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$choice = Read-Host "Opção (1-6)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "🚀 Iniciando PreçoBot..." -ForegroundColor Green
        Write-Host ""
        & $PYTHON main.py
    }
    "2" {
        Write-Host ""
        Write-Host "🧪 Executando todos os testes..." -ForegroundColor Green
        Write-Host ""
        Write-Host "=== Teste 1: Configuração ===" -ForegroundColor Cyan
        & $PYTHON test_bot_start.py
        Write-Host ""
        Write-Host "=== Teste 2: Sites ===" -ForegroundColor Cyan
        & $PYTHON test_sites.py
        Write-Host ""
        Write-Host "=== Teste 3: Scrapers ===" -ForegroundColor Cyan
        & $PYTHON test_scrapers.py
        Write-Host ""
        Write-Host "✅ Todos os testes concluídos!" -ForegroundColor Green
    }
    "3" {
        Write-Host ""
        Write-Host "📊 Testando scrapers..." -ForegroundColor Green
        & $PYTHON test_scrapers.py
    }
    "4" {
        Write-Host ""
        Write-Host "🌐 Testando sites..." -ForegroundColor Green
        & $PYTHON test_sites.py
    }
    "5" {
        Write-Host ""
        Write-Host "⚙️  Verificando configuração..." -ForegroundColor Green
        & $PYTHON test_bot_start.py
    }
    "6" {
        Write-Host ""
        Write-Host "👋 Saindo..." -ForegroundColor Yellow
        exit 0
    }
    default {
        Write-Host ""
        Write-Host "❌ Opção inválida!" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ Operação concluída!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
