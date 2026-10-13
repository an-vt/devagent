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

The `.env` file is loaded automatically and is not committed to Git. VS Code
can launch the same module through the **Debug devagent** configuration.
