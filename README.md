# tommyrobins91.github.io

Source for [tommyrobins91.github.io](https://tommyrobins91.github.io), my portfolio of real estate data tools, models and research.

## Editing

The pages are generated. Don't edit `index.html` or `projects/*.html` by hand.

- `build.py` holds the project list (title, date, category, card text, links, screenshot or stat panel) and the page templates.
- `content/<slug>.html` holds the body of each case study.
- `style.css` is shared by every page.

To rebuild after a change:

```
python3 build.py
```

Interactive demos live in `demos/<name>/index.html` and share `demos/demo.css`. They run on fictional data only. Card previews in `img/` are screenshots of the demos.

To add a project, add an entry to `PROJECTS` in `build.py`, write `content/<slug>.html`, and drop a screenshot in `img/` if there is one.

## Rules

No real owner names, target lists, deal figures, loan data or ACG addresses on the public site. Demos use public records or sample data.
