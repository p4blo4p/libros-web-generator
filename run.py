# run.py
from app import create_app

app = create_app()

if __name__ == '__main__':
    # No uses app.run() directamente en producción con este servidor de desarrollo.
    # Usa un servidor WSGI como Gunicorn o uWSGI.
    app.run(debug=True) # debug=True es para desarrollo
    
    
    