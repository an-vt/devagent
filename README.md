# devagent

## Requirements

- Python 3.11 or newer

## Development setup

Create and activate a virtual environment, then install the project and its
development dependencies:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Create the local environment file and add your API key:

```sh
cp .env.example .env
```

Start the interactive agent from the repository root:

```sh
python -m src
```

After installation, the equivalent console command is:

```sh
devagent
```

The agent can run shell commands, read and search files, and create, overwrite,
or edit files. `glob` and `grep` are read-only. In the interactive CLI,
`bash`, `edit_file`, and `write_file` calls pause for approval:

```text
permission requested: edit_file({'file_path': 'notes.txt', ...})
  [y] allow once  [a] always allow this tool  [n] deny:
```

Use `y` to allow one call, `a` to remember approval for that tool, or `n` to
refuse it. For non-interactive use, pass `--yes` to approve tool calls
automatically.

The `.env` file is loaded automatically and is not committed to Git. VS Code
can launch the same module through the **Debug devagent** configuration.
Hello
hello1
