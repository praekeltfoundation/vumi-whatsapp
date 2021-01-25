# vumi-whatsapp
A WhatsApp transport for Vumi


## Development
This project uses [poetry](https://python-poetry.org/docs/) for packaging and dependancy
management. Once poetry is installed, install dependancies by running
```bash
poetry install
```

To run a local server, run
```bash
poetry run sanic --debug --access vxwhatsapp.main.app
```

To run autoformatting and linting, run
```bash
poetry run black .
poetry run isort .
poetry run mypy .
poetry run flake8
```

## Configuration
Configuration is done through the following environment variables:

`SENTRY_DSN` - if present, sets up the sentry integration and pushes to the configured
DSN
