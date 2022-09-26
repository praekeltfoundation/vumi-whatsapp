FROM ghcr.io/praekeltfoundation/python-base-nw:3.9-bullseye as build

# Requirements to build wheels where there are no python 3.9 wheels
RUN apt-get-install.sh gcc libc-dev make
RUN pip install "poetry==1.2.0"
RUN poetry config virtualenvs.in-project true

# Install just the deps so we use cached layers if they haven't changed
COPY poetry.lock pyproject.toml ./
RUN poetry install --only main --no-root --no-interaction --no-ansi

# Build and install wheels to avoid editable installs
COPY . ./
RUN poetry build && .venv/bin/pip install dist/*.whl


FROM ghcr.io/praekeltfoundation/python-base-nw:3.9-bullseye

# Everything is installed in the venv, so no reason to copy . anymore
COPY --from=build .venv .venv

CMD ["./.venv/bin/sanic", "--host", "0.0.0.0", "vxwhatsapp.main.app"]
