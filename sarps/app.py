"""Entry point. Run with:  python app.py"""
from sarps import create_app

app = create_app()

if __name__ == "__main__":
    # debug=True reloads the server when you edit code and shows helpful
    # error pages. Never use debug mode on a public server.
    app.run(debug=True)
