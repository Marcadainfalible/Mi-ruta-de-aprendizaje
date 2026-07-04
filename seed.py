from app import create_app
from database import init_db


app = create_app()

with app.app_context():
    init_db()
    print("Base de datos inicializada.")
    print("Admin: admin@miruta.local / admin123")
    print("Docente: docente@miruta.local / docente123")
