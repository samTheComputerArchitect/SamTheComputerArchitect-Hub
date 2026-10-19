<div align="center">
  <img src="docs/banner.jpg" alt="The thumbnail editor and the research workbench" width="100%">
</div>

# SamTheComputerArchitect Hub

[![Python](https://img.shields.io/badge/python-3.12%2B-5294e2?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-6.1-092e20?style=flat-square&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/license-MIT-c084fc?style=flat-square)](LICENSE)
[![No build step](https://img.shields.io/badge/build-none%20needed-e2c452?style=flat-square)](#tech-stack)

**A self-hosted workspace for your projects, with the tools around them built in.** Keep
everything in one place and reach for the tool you need without switching apps — a thumbnail
editor with snapping guides, a freeform notes canvas, a research workbench for hypotheses and
experiments, and more on the way.

Inspired by [NeuralNine](https://github.com/samTheComputerArchitect) and the way it works:
small, focused tools for each part of the work, one after another, all in the same place.
Some of it is original — the thumbnail editor renders its own PNG export in the browser and
matches the canvas exactly, and the research workbench treats a hypothesis and its conclusion
as two separate steps, with every card showing which one you are at.

| Tool | What it does |
| --- | --- |
| **Thumbnails** | A 1280 × 720 canvas editor: layers, snapping guides, shapes, text, image filters, undo/redo, PNG export. |
| **Notes** | An infinite canvas for ink, sticky notes, headings and images, organised into notebooks → sections → tabs. |
| **Research** | Projects with tags and statuses, live search, and experiments with hypotheses, conclusions and file attachments. |
| **Videos / Editing** | Placeholders for the next two parts of the workflow. |
| **Settings** | API key storage (Ollama Cloud today) and a models panel. |

Everything runs locally on SQLite, with **no build step and no node_modules** — the front end
is hand written HTML, CSS and JavaScript served straight from `templates/` and `static/`.

## Install

```bash
git clone https://github.com/samTheComputerArchitect/SamTheComputerArchitect-Hub.git
cd SamTheComputerArchitect-Hub

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install "django>=6.1.2" "pillow>=13.0.0"

python manage.py migrate
python manage.py runserver
```

Then open <http://127.0.0.1:8000/>.

<details>
<summary>Prefer <code>uv</code>?</summary>

```bash
uv sync
uv run manage.py migrate
uv run manage.py runserver
```

</details>

## Getting started

```bash
python manage.py migrate            # create the database
python manage.py createsuperuser     # optional, for /admin/
python manage.py runserver           # http://127.0.0.1:8000/
```

## The tools

### Thumbnails

<div align="center">
  <img src="docs/editor.png" alt="The thumbnail editor" width="100%">
</div>

A canvas editor that lives in the browser and talks to Django over a small JSON API.

- **Three kinds of element** — images, text and shapes (rectangle, square, circle, triangle, line).
- **Direct manipulation** — drag to move, eight handles to resize, a handle to rotate, arrow
  keys to nudge (1 px, or 10 px with <kbd>Shift</kbd>).
- **Snapping** — to canvas edges, to the centre, and to other elements, with live guides. Hold
  <kbd>Alt</kbd> to switch it off. There is also equal-gap spacing, so three elements can be
  lined up with exactly the same distance between them.
- **Layer ordering** — bring to front, send to back, and the z-order survives a reload.
- **Per-type properties**
  - *Text* — font family, size, letter spacing, bold, italic, alignment, fill and outline.
  - *Shapes* — fill or no fill, outline colour, outline width, corner radius, thickness.
  - *Images* — brightness, contrast, saturation, hue and corner radius.
- **Undo / redo** — 40 steps of full document snapshots.
- **Templates** — load a designed layout and keep editing it.
- **PNG export** — rendered in the browser from the same geometry the canvas uses, so the file
  matches what you saw.
- **Autosave** — every edit is persisted in the background, and anything still pending is
  flushed if you close the tab.

### Notes

<div align="center">
  <img src="docs/notes.png" alt="The notes canvas" width="100%">
</div>

- Notebooks → sections → tabs, with the pan position remembered per tab.
- Freehand ink drawing with a configurable brush colour and width.
- Sticky notes and headings (`h1`, `h2`, `h3`) placed from a right-click menu.
- Images dropped or pasted onto the canvas, with resize and rotate handles.
- Pan and zoom, with a grid that stays glued to the content.

### Research

<div align="center">
  <img src="docs/research.png" alt="A research project" width="100%">
</div>

- **Projects** with an acronym, a full form, a short description and a long write-up.
- **Tags** (AI, Math, Software, Other) and **statuses** (Active, Paused, Finished), each with
  its own colour, stored in the database so you can restyle them from the admin.
- **Live search and filtering** — the grid updates as you type, with no page reload and no
  query string in the address bar. Tags and statuses compose with the search.
- **A page per project** — details in the header, experiments below as a four-across card grid.
- **Experiments** — title, description and hypothesis when you create it, and the conclusion
  afterwards, once the experiment has actually run. Every card says which state it is in.
- **File attachments** — any file type, up to 25 MB each, removable later.
- **A research paper page** per project. The editor is the next thing to build.

## Keyboard shortcuts

| Action | Shortcut |
| --- | --- |
| Undo | <kbd>Ctrl</kbd>+<kbd>Z</kbd> |
| Redo | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> |
| Duplicate the selection | <kbd>Ctrl</kbd>+<kbd>D</kbd> |
| Delete the selection | <kbd>Del</kbd> |
| Rename the thumbnail | Double-click the title |
| Add text at a point | Double-click the canvas |
| Nudge by 1 px / 10 px | Arrow keys / <kbd>Shift</kbd>+arrows |
| Pan the canvas | Middle-drag |
| Disable snapping | Hold <kbd>Alt</kbd> |
| Paste an image | <kbd>Ctrl</kbd>+<kbd>V</kbd> |
| Snap rotation to 15° | <kbd>Shift</kbd> while rotating |
| Export a PNG | <kbd>Ctrl</kbd>+<kbd>E</kbd> |
| Zoom to fit | <kbd>Ctrl</kbd>+<kbd>0</kbd> |

## Configuration

Everything lives in `SamTheComputerArchitectHub/settings.py`.

| Setting | Default | Notes |
| --- | --- | --- |
| `SECRET_KEY` | dev placeholder | Change this before deploying — it signs sessions and CSRF tokens. |
| `DEBUG` | `True` | Set to `False` in production. |
| `ALLOWED_HOSTS` | `[]` | Add your domain, e.g. `["hub.example.com"]`. |
| `DATABASES` | SQLite file | Swap for Postgres or MySQL when you outgrow it. |
| `STATIC_URL` / `STATICFILES_DIRS` | `static/` | Where the CSS, JS and images live. |
| `MEDIA_URL` / `MEDIA_ROOT` | `/media/`, `media/` | Where uploads are stored. |

For production, run `python manage.py collectstatic` and serve `staticfiles/` and `media/`
from your web server.

## Tech stack

| | |
| --- | --- |
| **Language** | Python 3.12+ |
| **Framework** | Django 6.1 |
| **Imaging** | Pillow 13 — server side sizing and upload validation |
| **Database** | SQLite by default |
| **Front end** | Vanilla HTML, CSS and JavaScript. No bundler, no framework, no CDN. |
| **Theming** | One dark theme built on CSS custom properties in `templates/base.html` |

## Layout

```
SamTheComputerArchitect-Hub/
├── SamTheComputerArchitectHub/   # Django project: settings, urls, wsgi, asgi
├── main/                         # Home page
├── notes/                        # Notes app
├── videos/                       # Videos page
├── editing/                      # Editing page
├── thumbnails/                   # Thumbnail editor
├── research/                     # Research app
│   └── templatetags/             # truncate_chars, get_item
├── settings/                     # Settings app (API keys)
├── templates/                    # Every page, one folder per app
│   ├── base.html                 # The theme: nav, modal, CSS variables
│   ├── research/                 # research, detail, experiment_form, paper
│   └── thumbnails/               # thumbnails, editor
├── static/
│   ├── js/research-common.js     # Shared modals for the research pages
│   └── Logo.png
├── docs/                         # Images used in this README
├── media/                        # Uploads (git ignored)
├── manage.py
└── pyproject.toml
```

## Development

```bash
git clone https://github.com/samTheComputerArchitect/SamTheComputerArchitect-Hub.git
cd SamTheComputerArchitect-Hub

python3 -m venv .venv && source .venv/bin/activate
python -m pip install "django>=6.1.2" "pillow>=13.0.0"

python manage.py migrate
python manage.py runserver
```

The dev server reloads on changes. `python manage.py test` runs the suite — it covers the
thumbnail API (element CRUD, uploads, colour validation, ownership), the research pages
(search, filters, the experiment workflow, the conclusion indicator) and the notes API.

Pull requests are welcome. Keep the front end dependency-free — if it can be done in plain
JavaScript, it should be — and match the existing style: the theme lives in
`templates/base.html`, and every app keeps its own styles in its own template.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

[NeuralNine](https://github.com/samTheComputerArchitect) for the original idea of building
small, focused tools for every part of the creative process, and for the workflow this is
built around.
