# Contab Office Pro - Versão Profissional

Sistema web para escritório de contabilidade feito em Python + Streamlit + SQLite.

## Recursos
- Login do escritório
- Portal do cliente
- Cadastro de clientes
- Cobranças mensais por competência
- Links de cobrança por WhatsApp e e-mail
- Tarefas mensais automáticas
- Financeiro
- Gestão de documentos
- Relatórios CSV
- Relatório do painel em PDF
- Configurações e usuários

## Login inicial do escritório
- Usuário: `admin`
- Senha: `123456`

## Como rodar localmente
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Como publicar online no Streamlit Cloud
1. Crie um repositório no GitHub.
2. Envie os arquivos `app.py`, `requirements.txt` e a pasta `.streamlit`.
3. Acesse https://share.streamlit.io
4. Escolha o repositório e publique o arquivo `app.py`.

## Observações
- O banco SQLite é criado automaticamente no primeiro uso.
- Os documentos ficam na pasta `documentos_clientes`.
- Para o portal do cliente, defina uma senha no cadastro do cliente.
