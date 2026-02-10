import os
import tempfile
import pytest
import io
from controle_system.app import create_app


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test.db"
    app = create_app(test_config={"DATABASE": str(db_file)})
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_crud(client):
    # create
    rv = client.post('/api/customers', json={"nome":"João","email":"joao@example.com","cpf":"12345678901"})
    assert rv.status_code == 201
    created = rv.get_json()
    cid = created['id']

    # read
    rv = client.get(f'/api/customers/{cid}')
    assert rv.status_code == 200
    data = rv.get_json()
    assert data['email'] == 'joao@example.com'

    # update
    rv = client.put(f'/api/customers/{cid}', json={"telefone":"+551199999"})
    assert rv.status_code == 200
    data = rv.get_json()
    assert data['telefone'] == '+551199999'

    # list
    rv = client.get('/api/customers')
    assert rv.status_code == 200
    arr = rv.get_json()
    assert any(c['id'] == cid for c in arr)

    # delete
    rv = client.delete(f'/api/customers/{cid}')
    assert rv.status_code == 200
    rv = client.get(f'/api/customers/{cid}')
    assert rv.status_code == 404


def test_export_import_and_auth(tmp_path):
    db_file = tmp_path / "test2.db"
    api_key = "test-key-123"
    app = create_app(test_config={"DATABASE": str(db_file), "API_KEY": api_key})
    app.config["TESTING"] = True
    client = app.test_client()

    # create two customers
    client.post('/api/customers', json={"nome":"AA","email":"a@example.com"}, headers={"X-API-KEY": api_key})
    client.post('/api/customers', json={"nome":"BB","email":"b@example.com"}, headers={"X-API-KEY": api_key})

    # export
    rv = client.get('/api/customers/export', headers={"X-API-KEY": api_key})
    assert rv.status_code == 200
    assert rv.headers['Content-Type'].startswith('text/csv')
    content = rv.data.decode('utf-8')
    assert 'a@example.com' in content and 'b@example.com' in content

    # import into a new DB
    db_file2 = tmp_path / "test3.db"
    app2 = create_app(test_config={"DATABASE": str(db_file2), "API_KEY": api_key})
    client2 = app2.test_client()
    # use token auth: register and login to get token on app2
    rvreg = client2.post('/auth/register', json={"username":"tuser","email":"t@example.com","password":"p"})
    assert rvreg.status_code == 201
    rvlogin = client2.post('/auth/login', json={"username":"tuser","password":"p"})
    assert rvlogin.status_code == 200
    token = rvlogin.get_json().get('token')
    data = io.BytesIO(content.encode('utf-8'))
    data.seek(0)
    rv = client2.post('/api/customers/import', data={"file": (data, 'clientes.csv')}, headers={"Authorization": f"Bearer {token}"}, content_type='multipart/form-data')
    assert rv.status_code == 200
    resp = rv.get_json()
    assert resp['created'] >= 2

