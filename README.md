# internship-finder

A local, single-user app for managing internship outreach: track companies,
contacts and every interaction on a timeline, draft French emails from
templates, polish them with a local LLM, review each one, and send from your
Hotmail account via the Microsoft Graph API.

Everything runs on your machine. Your data (database, CV, letters, auth tokens)
never leaves it.

---

## Milestones

| | Milestone | Status |
|---|---|---|
| **M0** | Scaffold: app boots, SQLite schema, settings page | ✅ done |
| **M1** | Companies, contacts, interaction timeline | ✅ done |
| **M2** | Templates + draft generation + LLM correction | ✅ done |
| **M3** | Microsoft Graph login + sending | ✅ done |
| **M4** | Reply ingestion, follow-up engine, llama-cpp backend, Docker | ✅ done |
| **M5** | Company domain + Excel export/import | 🚧 export + domain done; AI import next |

---

## Requirements

- **Python 3.12 or newer** (check with `python3 --version`)
- For M2 onward: a local LLM runtime (**Ollama**, set up below) — *not needed to run M0*

---

## Setup

From the project root (`internship-finder/`):

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the app

```bash
uvicorn app.main:app --reload
```

### 4. Open it

Go to **http://127.0.0.1:8000** in your browser.

- The **Dashboard** lists your companies; use **+ New company** to add one.
- Each company page tracks its email addresses (one marked primary), name
  variants, contacts, pipeline status, notes, and a **timeline** of interactions
  (calls, notes). Changing a company's status is logged on its timeline
  automatically.
- **Templates** holds reusable emails grouped by category (first-contact,
  follow-up, re-contact), with `{placeholders}` like `{company}` and `{my_name}`.
  A dozen French defaults are seeded (spontaneous/short/targeted applications,
  response to a posting, via-a-contact, relances, post-interview, reply to a
  rejection). Missing defaults are re-added on startup; edit or delete freely.
- **✉ Compose email** (on a company page) fills a template from that company's
  data, runs it through your local LLM for French polishing, and shows a review
  screen (edit / regenerate / switch template). Saving stores it as a *draft* on
  the timeline — nothing is sent yet. If the LLM isn't running, you still get the
  filled template and a notice to start it and hit **Regenerate**.
- **Send** a saved draft from the company timeline with **Send now** (requires a
  connected Microsoft account — see below). The CV and any per-company letter are
  attached automatically, and the draft is marked **sent**.
- **⟳ Sync inbox** (dashboard) pulls recent mail via Graph and logs replies on the
  matching company's timeline — matched by email thread or sender address. A reply
  clears that company from follow-up.
- **Needs follow-up** (dashboard) lists companies with no reply since your last
  email, past the cadence (default 7 days, overridable per company), each with a
  one-click *compose relance*.
- Each company has a **domain** field (e.g. `acme.com`), auto-filled from its
  first email — informational for now, and the basis for future email-finding.
- **⭳ Export .xlsx** (dashboard) writes a single grouped sheet matching your
  familiar columns: the company name appears once with one row per timeline event
  beneath it. (AI-assisted *import* of such sheets is the next step.)
- **Settings** lets you fill in your name, signature, sender email, global CV,
  LLM backend, and follow-up cadence. The **Account** page connects your Hotmail.

The SQLite database and all local files live in `data/` (created automatically,
and git-ignored). Delete that folder to start from a clean slate.

---

## Local LLM (needed from M2 onward — you can skip this for now)

The app talks to a pluggable LLM backend. The default is **Ollama**.

1. Install Ollama: <https://ollama.com/download>
2. Pull a French-capable model:
   ```bash
   ollama pull mistral-nemo
   ```
3. In **Settings**, set the backend to `ollama`, the model to `mistral-nemo`,
   and the base URL to `http://localhost:11434` (the defaults).

### Alternative: in-process llama-cpp (no separate server)

To run the model inside the app process instead of Ollama:

1. `pip install llama-cpp-python` (compiles a native extension; for GPU builds see
   the project's install docs).
2. Download a GGUF model file (e.g. a quantised Mistral-Nemo).
3. In **Settings**, set the backend to `llama_cpp` and *llama-cpp model path* to
   the `.gguf` file. No code changes needed.

---

## Microsoft account (for sending)

Sending from Hotmail uses the Microsoft Graph API with a one-time, free **Azure
app registration** and a **device-code login** — no password or client secret is
ever stored, only a refresh token in `data/graph_token_cache.json`.

### One-time app registration (~10 min)

1. Open the [Microsoft Entra admin center](https://entra.microsoft.com) →
   **App registrations** → **New registration**.
2. Name it (e.g. *internship-finder*). Under **Supported account types** choose
   **Personal Microsoft accounts only**. Click **Register**.
3. Go to **Authentication** → **Add a platform** → **Mobile and desktop
   applications**, tick `https://login.microsoftonline.com/common/oauth2/nativeclient`,
   set **Allow public client flows** to **Yes**, and **Save**.
4. Go to **API permissions** → **Add a permission** → **Microsoft Graph** →
   **Delegated permissions** → add **`Mail.Send`** and **`Mail.Read`**
   (`offline_access` is included automatically).
5. Copy the **Application (client) ID** from the **Overview** page.

### Connect

1. Paste the client ID into **Settings** → *Microsoft Graph*.
2. Go to the **Account** page → **Connect Microsoft account**.
3. Open the shown link, enter the code, and approve access. The page updates
   automatically once you're signed in.

### Sending

- Upload your **global CV** in **Settings** (PDF), and optionally a per-company
  **recommendation letter** on the company page.
- From a saved draft on a company's timeline, click **Send now**. The email goes
  out from your Hotmail with the CV (and letter, if present) attached, and the
  draft is marked **sent** on the timeline. Attachments must be under 3 MB each.

---

## Running with Docker (optional)

A `docker-compose.yml` runs the app alongside Ollama:

```bash
docker compose up --build
```

- The app is at **http://127.0.0.1:8000**; your data persists in `./data`.
- Ollama runs as a second service. Pull a model into it once:
  ```bash
  docker compose exec ollama ollama pull mistral-nemo
  ```
- In **Settings**, set the LLM base URL to `http://ollama:11434` so the app
  reaches Ollama over the compose network.

## Notes

- HTMX is currently loaded from a CDN (`unpkg.com`). For fully offline use,
  download `htmx.min.js` into `app/web/static/` and point the `<script>` tag in
  `app/web/templates/base.html` at it.
