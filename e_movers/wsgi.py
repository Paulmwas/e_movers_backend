# C:\Users\PC\Downloads\e_movers_backend\e_movers_backend\e_movers\wsgi.py
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "e_movers.settings")
application = get_wsgi_application()
