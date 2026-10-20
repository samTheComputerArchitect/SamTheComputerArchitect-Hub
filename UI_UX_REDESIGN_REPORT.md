# UI/UX Redesign Report — Research App

Layout-only redesign of the four research pages that sit behind `/research/`.
No visual style was introduced: every colour, font, radius, shadow and border
comes from the existing theme in `templates/base.html` or from the component
classes the pages already used.

**Date:** 2026-10-20
**Scope:** project detail, experiment form, experiment conclusion, research paper.
**Out of scope (untouched):** `templates/base.html`, `templates/research/research.html`,
every other app in the project.

---

## 1. What changed, page by page

### 1.1 Project detail — `/research/<pk>/` (`templates/research/detail.html`)

**Before:** the hero stacked identity → summary → a four-stat strip → an action
row, and the experiments only started below all of it. Status was shown twice
(the badge and the `STATUS` stat). The long Overview sat above the experiments.

**After:**

- **Compact hero.** Left column (`.project-identity`): acronym, full form and the
  short description. Right column (`.project-hero-side`, top aligned): the
  status badge, the tag chips, and directly under them the two action buttons
  in a new `.hero-actions` row — **Research Paper** (`.tool-btn-primary`) and
  **New Experiment** (`.tool-btn`).
- **The `.hero-stats` strip and the separate `.project-actions` row are gone.**
  Their content moved to the sidebar; `STATUS` was dropped as a duplicate of the
  badge.
- **Two columns below the hero** — `.detail-layout`, `minmax(0, 1fr) 320px`, gap 16:
  - `.col-main` — one `.panel` titled **EXPERIMENTS** with a `.panel-count`,
    holding `.experiment-grid`. The grid is now **2 columns** (3 at ≥1450,
    1 at ≤680) instead of 4, so titles are no longer cramped.
  - `.col-side` — **sticky, top 16**:
    - `.panel` **DETAILS** — Created / Experiments / Attachments as stacked
      `.detail-label` + `.stat-value` pairs.
    - `.panel` **OVERVIEW** — `project.details`, or the existing italic muted
      *"No long description yet."*
- The empty state (`.empty-note`) now sits **inside** the EXPERIMENTS panel.

### 1.2 Experiment form — `.../experiments/new/` and `.../edit/` (`templates/research/experiment_form.html`)

**Before:** one long column; the preview strip interrupted the title → fields
flow, the files block sat in the middle of the writing flow, and the save button
was 1000+ px below the title.

**After:**

- **The sticky `.topbar` is unchanged except for one addition:** the primary
  button (**Create experiment** / **Save changes**) now sits at its right end,
  to the right of the hint, and submits the form through `form="experiment-form"`.
  The topbar was moved out of the `<form>` element so the `form` attribute is
  what associates the button — there is now **exactly one submit button in the
  DOM**, so nothing can submit twice.
- **Two columns** — `.form-layout`, `minmax(0, 720px) 300px`, gap 32, centred
  (`.sheet` widened 720 → 1052):
  - `.col-main` — eyebrow, the large title input, **WHAT I DID**,
    **WHAT I EXPECTED**, and **WHAT HAPPENED** (edit mode only).
  - `.col-rail` — **sticky, top 68** (under the 52px topbar): the existing
    `.preview` strip, the **FILES** block (existing files with their Remove
    checkboxes, the file input and the selected-file chips), then a
    `.rail-actions` row with **Cancel** (`.btn-quiet`) and the save hint.
- **The bottom action row was removed** from the main column.

### 1.3 Experiment conclusion — `.../experiments/<eid>/` (`templates/research/experiment.html`)

**Before:** two recall blocks pushed the single editable field down, and the
buttons sat below a growing textarea.

**After:**

- `.sheet` widened 760 → 1000, now a two-column grid — `.write-layout`,
  `minmax(0, 320px) minmax(0, 640px)`, gap 40. The crumb, title and sub-line
  span the full sheet above the grid.
- **Left (`.col-recall`, sticky top 16):** the `.recall` blocks **WHAT I DID**
  and **WHAT I EXPECTED**, unchanged.
- **Right (`.col-write`):** the `.prompt` **WHAT HAPPENED**, the help text, the
  `.conclusion-input`, and the `.sheet-actions` row **immediately under the
  textarea** (Save/Add conclusion · Edit all details · status note).
- If neither recall field has content, the grid collapses to a single centred
  column (`.write-layout.no-recall`).

### 1.4 Research paper — `/research/<pk>/paper/` (`templates/research/paper.html`)

**Before:** a dead-end placeholder with no orientation.

**After:**

- `.paper-layout`, `300px minmax(0, 1fr)`, gap 16:
  - **Left:** a `.panel` titled **EXPERIMENTS** with a `.panel-count`, listing
    the real experiments of the project. Every entry is a link to the
    experiment page and carries the existing `.experiment-status` pill
    (conclusion added / no conclusion yet). Empty projects get the existing
    `.empty-note`.
  - **Right:** the `.paper-shell` placeholder, unchanged.
- `research/views.py` — `paper()` now passes the project's `experiments` to the
  template. This is the only backend change in the redesign.

---

## 2. Responsive behaviour

| Breakpoint | Project detail | Experiment form | Conclusion | Paper |
|---|---|---|---|---|
| ≥1450 | experiment grid 3 across | — | — | — |
| ≤1060 | sidebar drops below the main column (Details, then Overview) | rail moves below the fields, ordered **Files → Preview → Cancel** | single column, **writing area first**, recall below it (CSS `order`) | shell first, experiment panel below it |
| ≤700 | hero stacks: identity above the badge row, buttons wrap under it | — | — | — |
| ≤680 | experiment cards 1 across | — | — | — |
| <700px **viewport height** | — | — | sticky recall is disabled so it cannot overlap | — |

---

## 3. Style discipline

- **Nothing visual was added.** All new classes are layout-only wrappers:
  `.detail-layout`, `.col-main`, `.col-side`, `.detail-pair`, `.hero-actions`,
  `.form-layout`, `.col-rail`, `.rail-actions`, `.write-layout`, `.col-recall`,
  `.col-write`, `.paper-layout`, `.paper-exp-list`. They carry grid/flex
  placement, column counts, `order`, `position: sticky` and margins — no
  colour, border, radius or shadow.
- Reused unchanged: `.panel`, `.panel-title`, `.panel-count`, `.panel-body`,
  `.tool-btn`, `.tool-btn-primary`, `.experiment-card`, `.experiment-link`,
  `.experiment-title`, `.experiment-status`, `.status-badge`, `.research-tag`,
  `.recall`, `.field`, `.btn-primary`, `.btn-quiet`, `.back-link`,
  `.sheet-crumb`, `.topbar`, `.existing-file`, `.selected-file`, `.preview`,
  `.empty-note`.
- `templates/base.html` and `templates/research/research.html` were not touched.
  The known nav gap (`research_experiment` missing from the Research-active
  list) was deliberately left as is.
- The paper page copies the `.panel*`, `.experiment-link`, `.experiment-title`
  and `.experiment-status` rules verbatim from `detail.html`. Each template
  keeps its own styles in this project and `base.html` is locked, so the values
  were duplicated rather than invented — they are byte-for-byte the same
  declarations.

---

## 4. Verification

**Tests** — `python manage.py test` → **174 passed, 0 failed**.

Two existing tests encoded the *old* layout and were updated (they are design
tests, not behaviour tests):

- `test_project_page_has_the_details_in_the_hero` →
  `test_project_page_has_the_details_in_the_sidebar` (the hero no longer has a
  stats strip; the sidebar has the details; `Status` is not repeated).
- `test_experiments_are_rendered_as_cards_without_a_panel` →
  `test_experiments_are_rendered_as_cards_inside_the_panel` (the cards now sit
  in an EXPERIMENTS panel with a count).

Nine tests were added:

| Test | Covers |
|---|---|
| `test_the_hero_carries_the_primary_actions` | both action buttons live in the hero |
| `test_the_empty_state_sits_inside_the_experiments_panel` | empty state inside the panel |
| `test_the_paper_page_lists_the_experiments` | real experiments, status pills, working links |
| `test_the_paper_page_shows_the_empty_state_without_experiments` | paper empty state |
| `test_the_form_submits_from_the_top_bar` | `form="experiment-form"`, exactly one submit button |
| `test_the_form_submits_once` | one POST creates one experiment |
| `test_the_conclusion_page_is_a_two_column_layout` | grid, column order, field inside the right column |
| `test_the_conclusion_page_collapses_without_any_context` | `no-recall` collapse |

**Rendering** — every page was rendered in headless Chromium (Playwright) at
1440, 1000 and 640 px wide and inspected:

- detail: hero actions in the right column, EXPERIMENTS panel first, sidebar
  below it at ≤1060, one card per row at ≤680;
- form: topbar button on the right, rail on the right at 1440, rail below the
  fields ordered Files → Preview → Cancel at 1000;
- conclusion: recall left / writing area right at 1440, writing area first at
  640;
- paper: experiment panel left, shell right; shell first at 1000.

**Behaviour** — checked in the browser, not only in the markup:

- clicking the topbar button issues **exactly one POST** and creates exactly
  one experiment (the form is not submitted twice);
- the live preview still updates while typing the title;
- the delete confirmation still opens the shared site modal with the
  `data-confirm` text (no `window.confirm`);
- the status badge still opens the Change Status modal with the three options.

**Sticky** — measured by scrolling:

- the detail sidebar pins at `top: 16px` once the experiment column is taller
  than the sidebar;
- the form rail pins at `top: 68px`, directly under the sticky topbar;
- the conclusion recall pins at `top: 16px`, and switches to `position: static`
  below a 700px viewport height.

The local SQLite file was seeded with throwaway data for the visual checks and
restored to its original state afterwards (no rows added or left behind).

---

## 5. Files changed

| File | Change |
|---|---|
| `templates/research/detail.html` | two-column layout, compact hero, sidebar |
| `templates/research/experiment_form.html` | two-column layout, sticky rail, topbar submit |
| `templates/research/experiment.html` | two-column layout, sticky recall |
| `templates/research/paper.html` | experiment panel beside the placeholder shell |
| `research/views.py` | `paper()` passes `experiments` to the template |
| `research/tests.py` | 2 design tests updated, 9 tests added |

---

## 6. Notes for the next round

1. The project page duplicates its status: the hero badge shows it and the
   sidebar deliberately does not. If the badge ever moves out of the hero, the
   sidebar needs the label back.
2. `detail.html`, `paper.html` and `experiment_form.html` now each carry their
   own copies of the `.panel*`, `.experiment-*` and `.empty-note` rules. A
   shared partial would remove the duplication, but that means touching
   `base.html`, which this round was not allowed to do.
3. The experiment grid is 2 across by default and 3 from 1450px. On a wide
   monitor the main column is wide enough for 3, but never 4 — the old 4-across
   layout is what made the titles wrap.
4. The paper page is still a placeholder. The experiment list beside it is the
   natural input panel for the editor that comes next.
