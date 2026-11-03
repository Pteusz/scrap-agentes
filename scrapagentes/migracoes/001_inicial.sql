-- Esquema inicial (SPEC, seção 3). Chaves estrangeiras são ligadas pela conexão.

CREATE TABLE item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rede TEXT NOT NULL,
    url TEXT NOT NULL,
    conta TEXT,
    nicho TEXT NOT NULL,
    formato TEXT NOT NULL,
    data_publicacao TEXT,
    legenda TEXT,
    duracao_s REAL,
    texto TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    UNIQUE (rede, url)
);
CREATE INDEX idx_item_nicho ON item (nicho);
CREATE INDEX idx_item_formato ON item (formato);
CREATE INDEX idx_item_conta ON item (conta);
CREATE INDEX idx_item_data ON item (data_publicacao);

CREATE TABLE imagem (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES item (id) ON DELETE CASCADE,
    ordem INTEGER NOT NULL,
    arquivo TEXT NOT NULL,
    segundo REAL,
    marcador TEXT CHECK (marcador IN ('comeco', 'meio', 'fim')),
    UNIQUE (item_id, ordem)
);

CREATE TABLE metrica (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES item (id) ON DELETE CASCADE,
    coletado_em TEXT NOT NULL,
    nome TEXT NOT NULL,
    valor REAL NOT NULL
);
CREATE INDEX idx_metrica_item ON metrica (item_id, coletado_em);
CREATE INDEX idx_metrica_nome ON metrica (nome);

CREATE TABLE subnicho (
    item_id INTEGER NOT NULL REFERENCES item (id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (item_id, tag)
);
CREATE INDEX idx_subnicho_tag ON subnicho (tag);

CREATE TABLE job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER REFERENCES item (id) ON DELETE SET NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('ingestao', 'coleta')),
    estado TEXT NOT NULL CHECK (estado IN ('pendente', 'executando', 'concluido', 'erro')),
    tentativas INTEGER NOT NULL DEFAULT 0,
    erro TEXT,
    parametros TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE INDEX idx_job_estado ON job (estado);

-- Busca de texto livre sobre legenda e texto falado. Mantida pelo serviço (rowid = item.id).
CREATE VIRTUAL TABLE busca USING fts5 (
    legenda,
    texto,
    tokenize = 'unicode61 remove_diacritics 2'
);
