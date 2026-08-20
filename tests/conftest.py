# relativo ao diretório deste conftest (tests/)
# test_live_scrapers / test_antibot / test_live_lightpanda exigem browser/lightpanda
# real e rede → fora do CI unitário
collect_ignore = ["test_live_scrapers.py", "test_antibot.py", "test_live_lightpanda.py"]
