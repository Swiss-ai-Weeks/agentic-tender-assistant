# Sample tenders

Drop 3–5 real simap.ch tender PDFs here for local testing. Tender documents
themselves are **not committed** (see `.gitignore`) — they may not be freely
redistributable and can be large; only this README is tracked.

Expected layout — one subfolder per tender, containing all of its documents
(notice, cahier des charges, annexes):

```
data/sample_tenders/
  <tender-id-or-slug>/
    notice.pdf
    cahier_des_charges.pdf
    annexe_a.pdf
    ...
```

`src/pipeline.py` takes a tender folder path and globs `*.pdf` inside it.
