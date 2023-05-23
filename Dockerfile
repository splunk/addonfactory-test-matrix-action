FROM python:3.10.5

RUN python -m venv /venv
RUN . /venv/bin/activate
COPY . .
RUN pip install -r requirements.txt

COPY /entrypoint.sh /

WORKDIR /github/workspace
ENTRYPOINT ["/entrypoint.sh"]
