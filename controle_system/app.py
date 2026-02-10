from flask import Flask, request, jsonify, render_template, send_file
from flask_sqlalchemy import SQLAlchemy
from marshmallow import Schema, fields, validate, ValidationError, post_load
from datetime import datetime
import re
import os
import io
import csv
import logging
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

db = SQLAlchemy()

# simple token serializer (uses app.secret_key later)
serializer = None

class Customer(db.Model):
    __tablename__ = "customers"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    telefone = db.Column(db.String(30))
    endereco = db.Column(db.String(255))
    cpf = db.Column(db.String(20), unique=True)
    data_nascimento = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "email": self.email,
            "telefone": self.telefone,
            "endereco": self.endereco,
            "cpf": self.cpf,
            "data_nascimento": self.data_nascimento,
            "created_at": self.created_at.isoformat(),
        }


class CustomerSchema(Schema):
    id = fields.Int(dump_only=True)
    nome = fields.Str(required=True, validate=validate.Length(min=2))
    email = fields.Email(required=True)
    telefone = fields.Str(required=False)
    endereco = fields.Str(required=False)
    cpf = fields.Str(required=False)
    data_nascimento = fields.Str(required=False)

    @post_load
    def clean(self, data, **kwargs):
        if "cpf" in data and data["cpf"]:
            digits = re.sub(r"\D", "", data["cpf"])
            if len(digits) != 11:
                raise ValidationError("CPF deve conter 11 dígitos numéricos.")
            data["cpf"] = digits
        return data


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pwd):
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd):
        return check_password_hash(self.password_hash, pwd)


def create_app(test_config=None):
    app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))
    # set a secret key for sessions and token signing
    if test_config and test_config.get('SECRET'):
        app.secret_key = test_config.get('SECRET')
    else:
        app.secret_key = os.environ.get('APP_SECRET') or 'dev-secret'
    db_path = test_config.get("DATABASE") if test_config else os.path.join(os.path.dirname(__file__), "clientes.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    # API key configuration: allow overriding via test_config for tests
    if test_config and test_config.get("API_KEY") is not None:
        app.config["API_KEY"] = test_config.get("API_KEY")
    else:
        app.config["API_KEY"] = os.environ.get("APP_API_KEY")

    # init serializer for tokens
    global serializer
    serializer = URLSafeTimedSerializer(app.secret_key)

    # setup login manager
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    # ensure tables are created after models are defined
    with app.app_context():
        db.create_all()

    customer_schema = CustomerSchema()
    customers_schema = CustomerSchema(many=True)

    # Setup logging
    logger = logging.getLogger("controle_system")
    logger.setLevel(logging.INFO)
    log_path = os.path.join(os.path.dirname(__file__), "controle.log")
    if not logger.handlers:
        fh = logging.FileHandler(log_path)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)

    @app.errorhandler(ValidationError)
    def handle_marshmallow(err):
        return jsonify({"errors": err.messages}), 400

    def require_api_key(func):
        from functools import wraps

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = app.config.get("API_KEY")
            # allow session-authenticated users
            if current_user.is_authenticated:
                return func(*args, **kwargs)
            if not key:
                # no API key configured: allow access
                return func(*args, **kwargs)
            provided = request.headers.get("X-API-KEY") or request.args.get("api_key")
            if provided == key:
                return func(*args, **kwargs)
            # check bearer token
            auth = request.headers.get("Authorization")
            if auth and auth.startswith('Bearer '):
                token = auth.split(' ', 1)[1].strip()
                try:
                    data = serializer.loads(token, max_age=3600)
                    user = User.query.get(data.get('user_id'))
                    if user:
                        # consider user authenticated for this request
                        return func(*args, **kwargs)
                except (BadSignature, SignatureExpired):
                    pass
            return jsonify({"error": "Unauthorized"}), 401

        return wrapper

    @app.route("/", methods=["GET"])
    def index():
        return render_template("index.html")

    @app.route("/api/customers", methods=["GET"])
    def list_customers():
        customers = Customer.query.order_by(Customer.created_at.desc()).all()
        return jsonify(customers_schema.dump(customers)), 200

    @app.route("/api/customers/<int:cid>", methods=["GET"])
    def get_customer(cid):
        c = Customer.query.get_or_404(cid)
        return jsonify(customer_schema.dump(c)), 200

    @app.route("/api/customers", methods=["POST"])
    @require_api_key
    def create_customer():
        payload = request.get_json(force=True)
        data = customer_schema.load(payload)
        if "email" in data and Customer.query.filter_by(email=data["email"]).first():
            return jsonify({"error": "Email já cadastrado."}), 400
        if "cpf" in data and data.get("cpf") and Customer.query.filter_by(cpf=data.get("cpf")).first():
            return jsonify({"error": "CPF já cadastrado."}), 400
        c = Customer(**data)
        db.session.add(c)
        db.session.commit()
        logger.info(f"create id={c.id} email={c.email}")
        return jsonify(customer_schema.dump(c)), 201

    # Authentication endpoints
    @app.route('/auth/register', methods=['POST'])
    def register():
        payload = request.get_json(force=True)
        username = payload.get('username')
        email = payload.get('email')
        password = payload.get('password')
        if not username or not email or not password:
            return jsonify({'error': 'username,email,password required'}), 400
        if User.query.filter((User.username == username) | (User.email == email)).first():
            return jsonify({'error': 'usuario ou email já existe'}), 400
        u = User(username=username, email=email)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        return jsonify({'id': u.id, 'username': u.username, 'email': u.email}), 201

    @app.route('/auth/login', methods=['POST'])
    def login():
        payload = request.get_json(force=True)
        username = payload.get('username')
        password = payload.get('password')
        if not username or not password:
            return jsonify({'error': 'username,password required'}), 400
        user = User.query.filter((User.username == username) | (User.email == username)).first()
        if not user or not user.check_password(password):
            return jsonify({'error': 'Credenciais inválidas'}), 401
        login_user(user)
        token = serializer.dumps({'user_id': user.id})
        logger.info(f"login user_id={user.id}")
        return jsonify({'message': 'ok', 'token': token}), 200

    @app.route('/auth/logout', methods=['POST'])
    @login_required
    def logout():
        uid = current_user.get_id()
        logout_user()
        logger.info(f"logout user_id={uid}")
        return jsonify({'message': 'logged out'}), 200

    @app.route('/api/me', methods=['GET'])
    def api_me():
        if current_user.is_authenticated:
            return jsonify({'id': current_user.id, 'username': current_user.username, 'email': current_user.email}), 200
        return jsonify({'error': 'not authenticated'}), 401

    @app.route('/admin/users', methods=['GET'])
    @login_required
    def admin_users():
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template('admin_users.html', users=users)

    @app.route('/admin/users/create', methods=['POST'])
    @login_required
    def admin_create_user():
        payload = request.get_json(force=True)
        username = payload.get('username')
        email = payload.get('email')
        password = payload.get('password')
        if not username or not email or not password:
            return jsonify({'error': 'username,email,password required'}), 400
        if User.query.filter((User.username == username) | (User.email == email)).first():
            return jsonify({'error': 'usuario ou email já existe'}), 400
        u = User(username=username, email=email)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        return jsonify({'id': u.id, 'username': u.username, 'email': u.email}), 201

    @app.route('/admin/users/<int:uid>', methods=['DELETE'])
    @login_required
    def admin_delete_user(uid):
        if int(current_user.get_id()) == uid:
            return jsonify({'error': 'cannot delete yourself'}), 400
        u = User.query.get_or_404(uid)
        db.session.delete(u)
        db.session.commit()
        return jsonify({'deleted': True}), 200

    @app.route("/api/customers/<int:cid>", methods=["PUT"])
    @require_api_key
    def update_customer(cid):
        c = Customer.query.get_or_404(cid)
        payload = request.get_json(force=True)
        data = customer_schema.load(payload, partial=True)
        if "email" in data and data["email"] != c.email:
            if Customer.query.filter_by(email=data["email"]).first():
                return jsonify({"error": "Email já cadastrado."}), 400
        if "cpf" in data and data.get("cpf") != c.cpf:
            if data.get("cpf") and Customer.query.filter_by(cpf=data.get("cpf")).first():
                return jsonify({"error": "CPF já cadastrado."}), 400
        for k, v in data.items():
            setattr(c, k, v)
        db.session.commit()
        logger.info(f"update id={c.id} email={c.email}")
        return jsonify(customer_schema.dump(c)), 200

    @app.route("/api/customers/<int:cid>", methods=["DELETE"])
    @require_api_key
    def delete_customer(cid):
        c = Customer.query.get_or_404(cid)
        db.session.delete(c)
        db.session.commit()
        logger.info(f"delete id={cid}")
        return jsonify({"deleted": True}), 200

    @app.route("/api/customers/export", methods=["GET"])
    @require_api_key
    def export_customers():
        customers = Customer.query.order_by(Customer.created_at.desc()).all()
        si = io.StringIO()
        writer = csv.writer(si)
        writer.writerow(["id", "nome", "email", "telefone", "endereco", "cpf", "data_nascimento", "created_at"])
        for c in customers:
            writer.writerow([c.id, c.nome, c.email, c.telefone or "", c.endereco or "", c.cpf or "", c.data_nascimento or "", c.created_at.isoformat()])
        mem = io.BytesIO()
        mem.write(si.getvalue().encode("utf-8"))
        mem.seek(0)
        logger.info(f"export count={len(customers)}")
        return send_file(mem, mimetype="text/csv", download_name="customers.csv", as_attachment=True)

    @app.route("/api/customers/import", methods=["POST"])
    @require_api_key
    def import_customers():
        if 'file' not in request.files:
            return jsonify({"error": "file not provided"}), 400
        f = request.files['file']
        stream = io.StringIO(f.stream.read().decode('utf-8'))
        reader = csv.DictReader(stream)
        created = 0
        errors = []
        for i, row in enumerate(reader, start=1):
            try:
                data = {
                    'nome': row.get('nome') or row.get('name') or '',
                    'email': row.get('email') or '',
                    'telefone': row.get('telefone') or row.get('phone') or '',
                    'endereco': row.get('endereco') or row.get('address') or '',
                    'cpf': row.get('cpf') or '',
                    'data_nascimento': row.get('data_nascimento') or row.get('birth') or '',
                }
                payload = customer_schema.load(data)
                if payload.get('email') and Customer.query.filter_by(email=payload['email']).first():
                    continue
                # normalize empty cpf to None to avoid UNIQUE '' collisions
                if not payload.get('cpf'):
                    payload['cpf'] = None
                c = Customer(**payload)
                db.session.add(c)
                created += 1
            except Exception as e:
                errors.append({'line': i, 'error': str(e)})
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            errors.append({'line': 'commit', 'error': str(e)})
        logger.info(f"import created={created} errors={len(errors)}")
        return jsonify({'created': created, 'errors': errors}), 200

    # Expose Customer model for tests
    app.Customer = Customer
    app.db = db

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
