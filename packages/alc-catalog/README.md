# alc-catalog

A dependency-free local project discovery index shared by Agent commands and
LocalWeb. No Web installation, server, credentials, or database is required.

Commands register their explicit project directory before running. The index
stores paths only under `~/.alc/catalog/projects/`; `ALC_CATALOG_DIR` overrides
this location (use the same value in both entry points). Atomic per-project files
allow concurrent writers without lost updates. A failed registration warns on
stderr without failing document processing.

Readers discover durable Companion, translation, and OCR proofreading runs from
registered `.alc/` projects. Tasks remain owned by their original runtime;
LocalWeb does not enqueue or take control of them. Old projects can be registered
explicitly through LocalWeb's import action. The catalog does not scan the disk,
copy documents, retain secrets, or restore deleted project data. Moving a project
requires registering its new path. Invalid records are skipped independently.

Local OCR defaults live at `<catalog-root>/mineru.json`. A project's explicit
`.ac/mineru.json` wins, including when invalid. Web saves valid local executable
settings as the default; Agent materializes the inherited setting into each new
project before its availability check. Remote endpoints and token references are
never propagated through this local default. An existing installation can seed
the default explicitly without reinstalling MinerU.
