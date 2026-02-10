import sys
import csv
import json
from controle_system import create_app

def migrate(db_path, infile):
    app = create_app(test_config={"DATABASE": db_path})
    with app.app_context():
        from controle_system.app import Customer
        from controle_system.app import db
        created = 0
        if infile.lower().endswith('.csv'):
            with open(infile, encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    nome = row.get('nome') or row.get('name')
                    email = row.get('email')
                    cpf = row.get('cpf')
                    if not email or not nome: continue
                    if Customer.query.filter_by(email=email).first(): continue
                    c = Customer(nome=nome, email=email, cpf=cpf)
                    db.session.add(c)
                    created += 1
        else:
            with open(infile, encoding='utf-8') as f:
                arr = json.load(f)
                for row in arr:
                    nome = row.get('nome') or row.get('name')
                    email = row.get('email')
                    cpf = row.get('cpf')
                    if not email or not nome: continue
                    if Customer.query.filter_by(email=email).first(): continue
                    c = Customer(nome=nome, email=email, cpf=cpf)
                    db.session.add(c)
                    created += 1
        db.session.commit()
        print('created', created)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: migrate_clients.py <db_path> <infile.csv|.json>')
        sys.exit(1)
    migrate(sys.argv[1], sys.argv[2])
