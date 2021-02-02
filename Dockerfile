FROM praekeltfoundation/python-base:3.9-buster as build

# Requirements to build wheels where there are no python 3.9 wheels
RUN apt-get-install.sh gcc libc-dev make
RUN pip install "poetry==1.1.4"
COPY poetry.lock pyproject.toml ./
RUN poetry config virtualenvs.in-project true \
    && poetry install --no-dev --no-interaction --no-ansi --no-root

FROM praekeltfoundation/python-base:3.9-buster
COPY --from=build .venv/ .venv/
COPY . ./

CMD ["./.venv/bin/sanic", "--host", "0.0.0.0", "vxwhatsapp.main.app"]
