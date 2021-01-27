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

`HMAC_SECRET` - if present, validates Turn webhook signatures

`AMQP_URL` - How to connect to the AMQP server. Defaults to
`amqp://guest:guest@127.0.0.1/`

`TRANSPORT_NAME` - Determines the routing key when publishing and consuming messages
from the message broker. Defaults to `whatsapp`

`WHATSAPP_NUMBER` - The address of the whatsapp number that this transport is for

`PUBLISH_TIMEOUT` - The maximum amount of time to wait in seconds when publishing a
message to the message broker. Defaults to 10 seconds
