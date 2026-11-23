"""What a production server runs: `gunicorn wsgi:app`."""

from dance_judge import create_app

app = create_app()
