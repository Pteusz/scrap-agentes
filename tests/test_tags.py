from scrapagentes.tags import normalizar_tag, normalizar_tags


def test_minusculas_sem_acento_e_espacos():
    assert normalizar_tag("  Emagrecimento ") == "emagrecimento"
    assert normalizar_tag("Saúde   Mental") == "saude mental"
    assert normalizar_tag("AÇÃO") == "acao"


def test_normalizar_tags_remove_vazias_e_repetidas():
    assert normalizar_tags(["Dieta", "dieta ", "", "  ", "Treino"]) == ["dieta", "treino"]
    assert normalizar_tags(None) == []
