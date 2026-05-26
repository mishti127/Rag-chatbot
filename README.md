# Vectorless RAG (PageIndex-style)



Strict **document-only** Q&A without vector embeddings. Documents are organized into a **hierarchical page tree**, then retrieved via **reasoning-based tree navigation** ([overview](https://www.geeksforgeeks.org/artificial-intelligence/vectorless-rag-pageindex/)).



## Web UI (HTML / CSS / JavaScript)



Modern single-page frontend served by FastAPI.



```bash

python -m venv .venv

.venv\Scripts\activate

pip install -e .

copy .env.example .env   # add OPENROUTER_API_KEY



rag ingest sample_docs --user demo

rag serve

```



Open **http://127.0.0.1:8000/** — sign in with `demo` / `demo123`.



### UI features



- **Chat** — strict document Q&A

- **Documents** — upload PDF/TXT (drag & drop)

- **Notebook** — history of Q&A and summaries

- **Tools** — summarize from index

- **Profile** — theme (Ocean / Light / Forest), sign out



## CLI



```bash

rag ingest sample_docs --user demo

rag ask "Your question?" --user demo

rag ask --summarize "key points" --user demo

rag clear --user demo

rag serve --port 8000

```



## API



| Method | Path | Description |

|--------|------|-------------|

| POST | `/api/auth/login` | Get bearer token |

| GET | `/api/documents` | List indexed files |

| POST | `/api/documents/upload` | Upload PDF/TXT |

| POST | `/api/chat` | Strict Q&A |

| POST | `/api/summarize` | Document summary |



Frontend lives in [`frontend/`](frontend/) (`index.html`, `css/main.css`, `js/app.js`).



## Tests



```bash

pip install -e ".[dev]"

pytest

```

