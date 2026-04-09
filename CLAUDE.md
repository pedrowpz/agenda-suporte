# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the application

```bash
python agenda.py
```

No external dependencies — standard library only. No virtual environment needed.

## Architecture

Single-file application (`agenda.py`) with a procedural structure. All logic lives in one file:

- `main()` → calls `menu()`
- `menu()` → interactive loop; routes user input (1–6) to CRUD functions
- CRUD functions: `cadastrarContato`, `listarContato`, `buscarContatoPeloNome`, `atualizarContato`, `deletarContato`, `sair`

**Data storage:** `agenda.txt` — plain text, semicolon-delimited rows with format `ID;Name;Phone;Email\n`. All reads/writes go directly to this file; there is no in-memory data structure.

**Update flow:** `atualizarContato` deletes the old entry (rewrites the file excluding the matched line) then calls `cadastrarContato` to append the new values.

## Known bugs

- `buscarContatoPeloNome` (line ~85): `break` inside the loop exits after the first line, so only the first contact is ever checked.
- `deletarContato`/`atualizarContato`: comparison uses `.upper` (missing `()`) — call it as `.upper()`.
- File opened with bare `open()` in several places instead of `with` statements; an exception mid-write can leave `agenda.txt` in a corrupt state.

## Language note

Code, variable names, and comments are in Portuguese (`cadastrar` = register, `listar` = list, `deletar` = delete, `buscar` = search, `atualizar` = update, `sair` = exit). Keep this convention when editing.
