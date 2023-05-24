FROM python:3.11.3

RUN python -m venv /venv
RUN . /venv/bin/activate
COPY . .
RUN pip install -r requirements.txt

COPY /entrypoint.sh /

WORKDIR /github/workspace
ENTRYPOINT ["/entrypoint.sh"]
