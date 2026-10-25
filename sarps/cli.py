"""Terminal commands for setting things up. Run them with `flask --app app <command>`."""
import click
from sqlalchemy import select

from sarps.constants import Role
from sarps.extensions import db
from sarps.models import Department, User
from sarps.security import password_problems


def register_commands(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all database tables (safe to run again; it never deletes data)."""
        db.create_all()
        click.echo("Database tables are ready.")

    @app.cli.command("add-department")
    @click.argument("name")
    def add_department(name):
        """Add a department, e.g.  flask --app app add-department "Computer Science"."""
        name = name.strip()
        if not name:
            raise click.ClickException("Department name cannot be empty.")
        if db.session.scalar(select(Department).where(Department.name == name)):
            raise click.ClickException(f"Department '{name}' already exists.")
        db.session.add(Department(name=name))
        db.session.commit()
        click.echo(f"Added department: {name}")

    @app.cli.command("create-admin")
    @click.option("--name", prompt="Full name")
    @click.option("--email", prompt="Email")
    @click.password_option("--password", prompt="Password")
    def create_admin(name, email, password):
        """Create the first administrator account."""
        email = email.strip().lower()
        problems = password_problems(password, app.config["MIN_PASSWORD_LENGTH"])
        if problems:
            raise click.ClickException("Password needs: " + ", ".join(problems) + ".")
        if db.session.scalar(select(User).where(User.email == email)):
            raise click.ClickException("An account with that email already exists.")
        admin = User(full_name=name.strip(), email=email, role=Role.ADMIN)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"Administrator created: {email}")
