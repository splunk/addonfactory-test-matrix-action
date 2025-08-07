FROM python:alpine

RUN python -m venv /venv
RUN . /venv/bin/activate
COPY . .
RUN pip install -r requirements.txt

COPY /entrypoint.sh /

WORKDIR /github/workspace

ENTRYPOINT ["bash", "-x", "/entrypoint.sh"]
