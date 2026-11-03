import sqlite3


def test_saude_sem_chave_e_rotas_protegidas(cliente_sem_chave):
    assert cliente_sem_chave.get("/saude").json() == {"status": "ok"}
    for rota in ("/itens", "/jobs/1", "/itens/1/pacote", "/itens/1/imagens/1"):
        assert cliente_sem_chave.get(rota).status_code == 401, rota
    assert cliente_sem_chave.post("/itens", json={}).status_code == 401
    assert cliente_sem_chave.patch("/itens/1/subnichos", json={}).status_code == 401
    assert cliente_sem_chave.post("/itens/1/coletas").status_code == 401
    assert cliente_sem_chave.get("/itens", headers={"X-API-Key": "errada"}).status_code == 401


def test_sem_chave_configurada_nada_passa(config, tmp_path):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from scrapagentes.api import criar_app

    app = criar_app(replace(config, chave_api=None))
    with TestClient(app, headers={"X-API-Key": "qualquer"}) as c:
        assert c.get("/itens").status_code == 401


def test_documentacao_desligada_por_padrao(cliente):
    assert cliente.get("/docs").status_code == 404
    assert cliente.get("/openapi.json").status_code == 404


def test_criar_item_e_ler_job(envio, cliente):
    r = envio.foto(subnichos=["Dieta", "Treino"])
    assert r.status_code == 202
    corpo = r.json()
    job = cliente.get(f"/jobs/{corpo['job_id']}").json()
    assert job["estado"] == "concluido" and job["tipo"] == "ingestao"
    assert job["item_id"] == corpo["item_id"]
    assert cliente.get("/jobs/9999").status_code == 404


def test_duas_coletas_geram_dois_conjuntos_sem_sobrescrever(envio, cliente, config):
    item_id = envio.criar(envio.foto, curtidas="10", comentarios="2")
    r = cliente.post(f"/itens/{item_id}/coletas", json={"metricas": {"curtidas": 25, "comentarios": 4}})
    assert r.status_code == 202
    assert cliente.get(f"/jobs/{r.json()['job_id']}").json()["estado"] == "concluido"

    linhas = sqlite3.connect(config.banco).execute(
        "SELECT coletado_em, nome, valor FROM metrica WHERE item_id = ? ORDER BY coletado_em, nome",
        (item_id,),
    ).fetchall()
    assert len(linhas) == 4
    assert len({l[0] for l in linhas}) == 2
    primeira, segunda = linhas[:2], linhas[2:]
    assert {(n, v) for _, n, v in primeira} == {("curtidas", 10.0), ("comentarios", 2.0)}
    assert {(n, v) for _, n, v in segunda} == {("curtidas", 25.0), ("comentarios", 4.0)}

    pacote = cliente.get(f"/itens/{item_id}/pacote").json()
    assert pacote["metricas"]["valores"] == {"comentarios": 4.0, "curtidas": 25.0}


def test_coleta_sem_metricas_vira_job_com_erro(envio, cliente):
    item_id = envio.criar(envio.foto)
    r = cliente.post(f"/itens/{item_id}/coletas")
    job = cliente.get(f"/jobs/{r.json()['job_id']}").json()
    assert job["estado"] == "erro" and "nenhuma métrica" in job["erro"]
    assert cliente.post("/itens/9999/coletas").status_code == 404


def test_reingestao_nao_duplica_e_acrescenta_coleta(envio, cliente, config):
    primeiro = envio.criar(envio.foto, url="https://exemplo.test/p/1", curtidas="5")
    segundo = envio.criar(
        envio.foto, url="https://exemplo.test/p/1", curtidas="9", legenda="legenda nova",
        subnichos=["novo"],
    )
    assert primeiro == segundo
    banco = sqlite3.connect(config.banco)
    assert banco.execute("SELECT COUNT(*) FROM item").fetchone()[0] == 1
    assert banco.execute("SELECT COUNT(DISTINCT coletado_em) FROM metrica").fetchone()[0] == 2
    assert banco.execute("SELECT COUNT(*) FROM imagem").fetchone()[0] == 1  # mídia não reprocessada
    pacote = cliente.get(f"/itens/{primeiro}/pacote").json()
    assert pacote["contexto"]["legenda"] == "legenda nova"
    assert pacote["contexto"]["subnichos"] == ["novo"]
    assert pacote["metricas"]["valores"] == {"curtidas": 9.0}


def test_reingestao_sem_subnichos_preserva_os_existentes(envio, cliente):
    item_id = envio.criar(envio.foto, url="https://exemplo.test/p/2", subnichos=["dieta"])
    envio.criar(envio.foto, url="https://exemplo.test/p/2")
    assert cliente.get(f"/itens/{item_id}/pacote").json()["contexto"]["subnichos"] == ["dieta"]


def test_tags_equivalentes_viram_a_mesma_tag_e_a_mesma_busca(envio, cliente):
    a = envio.criar(envio.foto, url="manual:a", subnichos=["Emagrecimento "])
    b = envio.criar(envio.foto, url="manual:b", subnichos=["emagrecimento"])
    assert cliente.get(f"/itens/{a}/pacote").json()["contexto"]["subnichos"] == ["emagrecimento"]
    for consulta in ("Emagrecimento ", "emagrecimento", "EMAGRECIMENTO"):
        ids = {i["id"] for i in cliente.get("/itens", params={"subnicho": consulta}).json()["itens"]}
        assert ids == {a, b}


def test_busca_combinada_nicho_subnicho_formato_periodo(envio, cliente):
    a = envio.criar(envio.foto, url="manual:a", nicho="Saúde", subnichos=["dieta", "treino"],
                    data_publicacao="2026-01-10")
    b = envio.criar(envio.carrossel, url="manual:b", nicho="saude", subnichos=["dieta"],
                    data_publicacao="2026-02-10")
    c = envio.criar(envio.foto, url="manual:c", nicho="financas", subnichos=["dieta", "treino"],
                    data_publicacao="2026-03-10")

    def ids(**params):
        r = cliente.get("/itens", params=params)
        assert r.status_code == 200, r.text
        return {i["id"] for i in r.json()["itens"]}

    assert ids(nicho="saude") == {a, b}
    assert ids(nicho="saude", formato="foto") == {a}
    assert ids(subnicho=["dieta", "treino"]) == {a, c}                      # modo "todos"
    assert ids(subnicho=["treino", "inexistente"], modo_subnicho="qualquer") == {a, c}
    assert ids(subnicho=["treino", "inexistente"]) == set()
    assert ids(nicho="saude", subnicho="dieta", publicado_de="2026-02-01") == {b}
    assert ids(publicado_de="2026-01-15", publicado_ate="2026-02-28") == {b}
    assert ids(nicho="saude", subnicho=["dieta"], formato="foto",
               publicado_de="2026-01-01", publicado_ate="2026-01-31") == {a}
    assert ids(rede="manual", conta="conta_teste") == {a, b, c}
    assert ids(rede="instagram") == set()


def test_busca_por_metrica_usa_a_coleta_mais_recente(envio, cliente):
    a = envio.criar(envio.foto, url="manual:a", curtidas="100")
    b = envio.criar(envio.foto, url="manual:b", curtidas="10")
    sem = envio.criar(envio.foto, url="manual:c")
    cliente.post(f"/itens/{b}/coletas", json={"metricas": {"curtidas": 500}})  # b passa a 500
    cliente.post(f"/itens/{a}/coletas", json={"metricas": {"curtidas": 20}})   # a cai para 20

    def ids(**params):
        return {i["id"] for i in cliente.get("/itens", params=params).json()["itens"]}

    assert ids(metrica="curtidas", min=100) == {b}
    assert ids(metrica="curtidas", max=50) == {a}
    assert ids(metrica="curtidas", min=10, max=600) == {a, b}
    assert ids(metrica="curtidas") == {a, b}          # quem nunca teve a métrica não entra
    assert sem not in ids(metrica="visualizacoes")
    assert cliente.get("/itens", params={"min": 1}).status_code == 422


def test_busca_de_texto_livre_em_legenda(envio, cliente):
    a = envio.criar(envio.foto, url="manual:a", legenda="Receita de bolo de cenoura")
    envio.criar(envio.foto, url="manual:b", legenda="Treino de pernas")
    def ids(q):
        return {i["id"] for i in cliente.get("/itens", params={"q": q}).json()["itens"]}
    assert ids("bolo") == {a}
    assert ids("CENOURA") == {a}
    assert cliente.get("/itens", params={"q": '"'}).status_code in (200, 422)  # nunca 500


def test_paginacao(envio, cliente):
    for n in range(5):
        envio.criar(envio.foto, url=f"manual:{n}")
    r = cliente.get("/itens", params={"tamanho": 2, "pagina": 2}).json()
    assert r["total"] == 5 and len(r["itens"]) == 2 and r["pagina"] == 2
    assert cliente.get("/itens", params={"tamanho": 1000}).status_code == 422


def test_alterar_subnichos_sem_reprocessar(envio, cliente):
    item_id = envio.criar(envio.foto, subnichos=["a", "b"])
    url = f"/itens/{item_id}/subnichos"
    assert cliente.patch(url, json={"adicionar": ["C ", "a"]}).json()["subnichos"] == ["a", "b", "c"]
    assert cliente.patch(url, json={"remover": ["B"]}).json()["subnichos"] == ["a", "c"]
    assert cliente.patch(url, json={"substituir": ["Novo"]}).json()["subnichos"] == ["novo"]
    assert cliente.patch(url, json={"substituir": ["x"], "adicionar": ["y"]}).status_code == 422
    assert cliente.patch(url, json={"outro": []}).status_code == 422
    assert cliente.patch("/itens/9999/subnichos", json={"adicionar": ["x"]}).status_code == 404


def test_pacote_foto(envio, cliente):
    item_id = envio.criar(envio.foto, subnichos=["dieta"], curtidas="7", visualizacoes="70")
    p = cliente.get(f"/itens/{item_id}/pacote").json()
    assert set(p) == {"contexto", "metricas", "texto", "imagens"}
    assert p["contexto"] == {
        "rede": "manual", "link": p["contexto"]["link"], "conta": "conta_teste", "nicho": "saude",
        "subnichos": ["dieta"], "formato": "foto", "data_publicacao": "2026-03-10",
        "legenda": "legenda de teste", "duracao_s": None,
    }
    assert p["contexto"]["link"].startswith("manual:")
    assert p["metricas"]["valores"] == {"curtidas": 7.0, "visualizacoes": 70.0}
    assert p["metricas"]["coletado_em"]
    assert p["texto"] is None
    assert p["imagens"] == [{"ordem": 1, "rota": f"/itens/{item_id}/imagens/1"}]


def test_pacote_carrossel_em_ordem_e_arquivo_servido(envio, cliente, midias):
    item_id = envio.criar(envio.carrossel)
    p = cliente.get(f"/itens/{item_id}/pacote").json()
    assert [i["ordem"] for i in p["imagens"]] == [1, 2, 3]
    for ordem, original in enumerate(midias["slides"], start=1):
        r = cliente.get(p["imagens"][ordem - 1]["rota"])
        assert r.status_code == 200 and r.content == original.read_bytes()
    assert cliente.get(f"/itens/{item_id}/imagens/9").status_code == 404
    assert cliente.get("/itens/9999/pacote").status_code == 404


def test_video_guarda_duracao_e_pacote_tem_texto(envio, cliente, midias):
    item_id = envio.criar(envio.video, subnichos=["aula"])
    p = cliente.get(f"/itens/{item_id}/pacote").json()
    assert p["contexto"]["formato"] == "video"
    assert abs(p["contexto"]["duracao_s"] - midias["duracao_video_s"]) < 0.5
    assert p["texto"] == [] and p["imagens"] == []  # transcrição e frames chegam nas etapas 04 e 05


def test_pacote_de_video_com_texto_e_frames_ficticios(envio, cliente, config):
    """Estrutura do SPEC para vídeo, com texto e frames inseridos direto no banco."""
    import json
    item_id = envio.criar(envio.video)
    banco = sqlite3.connect(config.banco)
    trechos = [
        {"inicio_s": 0.0, "fim_s": 2.0, "texto": "abertura"},
        {"inicio_s": 4.0, "fim_s": 6.0, "texto": "fechamento"},
    ]
    banco.execute("UPDATE item SET texto = ? WHERE id = ?", (json.dumps(trechos), item_id))
    banco.executemany(
        "INSERT INTO imagem (item_id, ordem, arquivo, segundo, marcador) VALUES (?, ?, ?, ?, ?)",
        [(item_id, 1, "midia/x/1.png", 1.0, "comeco"), (item_id, 2, "midia/x/2.png", 3.0, "meio"),
         (item_id, 3, "midia/x/3.png", 5.5, "fim")],
    )
    banco.commit()
    p = cliente.get(f"/itens/{item_id}/pacote").json()
    assert p["texto"] == trechos
    assert [(i["ordem"], i["segundo"], i["marcador"], i["fala_proxima"]) for i in p["imagens"]] == [
        (1, 1.0, "comeco", "abertura"),
        (2, 3.0, "meio", "abertura"),      # 3.0 está a 1 s de "abertura" e a 1 s de "fechamento": vence o primeiro
        (3, 5.5, "fim", "fechamento"),
    ]


def test_busca_em_texto_falado(envio, cliente, config):
    import json
    from scrapagentes.banco import conectar, reindexar_busca
    item_id = envio.criar(envio.video)
    conn = conectar(config.banco)
    conn.execute("UPDATE item SET texto = ? WHERE id = ?",
                 (json.dumps([{"inicio_s": 0, "fim_s": 1, "texto": "hoje vamos falar de colágeno"}]), item_id))
    reindexar_busca(conn, item_id)
    conn.commit()
    ids = {i["id"] for i in cliente.get("/itens", params={"q": "colageno"}).json()["itens"]}
    assert ids == {item_id}


def test_erros_de_entrada(envio, cliente):
    assert envio.foto(nicho="").status_code == 422                       # nicho obrigatório ao criar
    assert envio.foto(rede="orkut").status_code == 422                   # rede desconhecida
    assert cliente.post("/itens", json={"url": "https://nada.test/x", "nicho": "a"}).status_code == 422
    assert cliente.post("/itens", content=b"oi", headers={"content-type": "text/plain"}).status_code == 422
    r = envio.foto(curtidas="muito")
    assert r.status_code == 422                                          # métrica não numérica


def test_erros_do_adaptador_viram_job_com_erro(envio, cliente):
    r = envio.foto(formato="reels")
    job = cliente.get(f"/jobs/{r.json()['job_id']}").json()
    assert job["estado"] == "erro" and job["erro"].startswith("formato_nao_suportado")
    assert r.json()["item_id"] is None

    r = envio.foto(conta="")
    job = cliente.get(f"/jobs/{r.json()['job_id']}").json()
    assert job["estado"] == "erro" and "conta" in job["erro"]


def test_reprocessar_regrava_as_imagens(envio, cliente, config):
    item_id = envio.criar(envio.carrossel, url="manual:r")
    pasta = config.dados / "midia" / str(item_id)
    (pasta / "002.png").unlink()
    envio.criar(envio.carrossel, url="manual:r")
    assert not (pasta / "002.png").exists()                              # sem reprocessar, nada muda
    envio.criar(envio.carrossel, url="manual:r", reprocessar="true")
    assert (pasta / "002.png").exists()


def test_chave_nao_ascii_da_401(cliente_sem_chave):
    r = cliente_sem_chave.get("/itens", headers={"X-API-Key": "ação".encode("latin-1")})
    assert r.status_code == 401


def test_tipos_errados_no_json_dao_422(cliente):
    for corpo in ({"url": 5, "nicho": "a"}, {"rede": "manual", "nicho": 5},
                  {"rede": "manual", "nicho": "a", "subnichos": "abc"}):
        assert cliente.post("/itens", json=corpo).status_code == 422, corpo


def test_reingestao_sem_legenda_preserva_a_legenda(envio, cliente):
    item_id = envio.criar(envio.foto, url="manual:l", legenda="original")
    envio.criar(envio.foto, url="manual:l", legenda="")
    assert cliente.get(f"/itens/{item_id}/pacote").json()["contexto"]["legenda"] == "original"


def test_falha_apos_gravar_midia_nao_deixa_pasta_orfa(envio, config, monkeypatch):
    from scrapagentes import servico

    def quebra(*a, **k):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(servico, "reindexar_busca", quebra)
    r = envio.foto(url="manual:q")
    assert r.status_code == 202 and r.json()["item_id"] is None
    midia = config.dados / "midia"
    assert not midia.exists() or list(midia.iterdir()) == []
